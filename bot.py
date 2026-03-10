import os
import re
import json
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

ARQUIVO_CACHE = "radar_investimentos_cache.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

YUBB_URL = "https://yubb.com.br/investimentos/renda-fixa"

# Benchmark aproximado
SELIC = 10.75
CDI = 13.25

# Regras do radar
CDB_DIARIO_MIN_CDI = 100.0
PRAZO_CURTO_MAX_DIAS = 30
ISENTO_MIN_CDI = 90.0

# -----------------------------
# ESTADO
# -----------------------------

def estado_padrao():
    return {
        "ranking": [],
        "diarios": [],
        "curtos": [],
        "isentos": [],
        "selicplus": [],
        "updated_at": None
    }


def carregar_estado():
    try:
        with open(ARQUIVO_CACHE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return estado_padrao()


def salvar_estado():
    with open(ARQUIVO_CACHE, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


estado = carregar_estado()

# -----------------------------
# HELPERS
# -----------------------------

def limpar_texto(txt: str) -> str:
    return re.sub(r"\s+", " ", (txt or "")).strip()


def parse_float_br(txt: str) -> float:
    if not txt:
        return 0.0
    txt = str(txt).strip()
    try:
        return float(txt.replace(".", "").replace(",", "."))
    except Exception:
        try:
            return float(txt.replace(",", "."))
        except Exception:
            return 0.0


def retorno_liquido_anual(tipo: str, taxa_cdi: float, prazo_dias: int = 365) -> float:
    bruto = (CDI / 100.0) * (taxa_cdi / 100.0)

    if tipo == "CDB":
        if prazo_dias <= 180:
            ir = 0.225
        elif prazo_dias <= 360:
            ir = 0.20
        elif prazo_dias <= 720:
            ir = 0.175
        else:
            ir = 0.15

        liquido = bruto * (1 - ir)
    else:
        # LCI/LCA isentas
        liquido = bruto

    return round(liquido * 100, 2)


def score_item(item: dict) -> float:
    score = 0.0

    taxa = item.get("taxa", 0.0)
    tipo = item.get("tipo", "")
    prazo = item.get("prazo_dias", 365)
    diaria = item.get("liquidez_diaria", False)
    fgc = item.get("fgc", False)

    if taxa >= 110:
        score += 4
    elif taxa >= 105:
        score += 3
    elif taxa >= 100:
        score += 2

    if diaria:
        score += 2

    if prazo <= 30:
        score += 2

    if fgc:
        score += 2

    if tipo in {"LCI", "LCA"}:
        score += 1

    return round(min(score, 10.0), 1)


def classificar(score: float) -> str:
    if score >= 9:
        return "🔴 Oportunidade forte"
    if score >= 7.5:
        return "🟡 Oportunidade muito boa"
    return "🟢 Oportunidade boa"

# -----------------------------
# PARSER YUBB
# -----------------------------

def extrair_produtos_yubb():
    r = requests.get(YUBB_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    texto = limpar_texto(soup.get_text(" ", strip=True))

    produtos = []

    padrao = re.finditer(
        r"(CDB|LCI|LCA).*?(\d{2,3}(?:[.,]\d{1,2})?)\s*%\s*CDI",
        texto,
        flags=re.IGNORECASE
    )

    vistos = set()

    for m in padrao:
        tipo = m.group(1).upper()
        taxa = parse_float_br(m.group(2))

        inicio = max(0, m.start() - 160)
        fim = min(len(texto), m.end() + 260)
        bloco = texto[inicio:fim]

        emissor = "Emissor não identificado"
        banco_match = re.search(
            r"(Itaú|Itau|Bradesco|Nubank|C6|Banco Inter|Inter|PagBank|Pine|BS2|Daycoval|Sofisa|BMG)",
            bloco,
            flags=re.IGNORECASE
        )
        if banco_match:
            emissor = limpar_texto(banco_match.group(1))

        liquidez_diaria = bool(re.search(r"liquidez diária|liquidez diaria", bloco, flags=re.IGNORECASE))
        fgc = "fgc" in bloco.lower()

        prazo_dias = 365
        prazo_match = re.search(r"(\d{1,4})\s*dias", bloco, flags=re.IGNORECASE)
        if prazo_match:
            prazo_dias = int(prazo_match.group(1))

        chave = (tipo, emissor.lower(), taxa, prazo_dias, liquidez_diaria)
        if chave in vistos:
            continue
        vistos.add(chave)

        item = {
            "tipo": tipo,
            "emissor": emissor,
            "taxa": taxa,
            "prazo_dias": prazo_dias,
            "liquidez_diaria": liquidez_diaria,
            "fgc": fgc or True,
        }

        item["retorno_liquido"] = retorno_liquido_anual(item["tipo"], item["taxa"], item["prazo_dias"])
        item["melhor_que_selic"] = item["retorno_liquido"] > SELIC
        item["score"] = score_item(item)
        item["classificacao"] = classificar(item["score"])

        produtos.append(item)

    return sorted(
        produtos,
        key=lambda x: (x["score"], x["retorno_liquido"], x["taxa"]),
        reverse=True
    )

# -----------------------------
# FILTROS DAS CATEGORIAS
# -----------------------------

def filtrar_diarios(produtos):
    return [
        p for p in produtos
        if p["tipo"] == "CDB"
        and p["liquidez_diaria"]
        and p["taxa"] >= CDB_DIARIO_MIN_CDI
    ]


def filtrar_curtos(produtos):
    return [
        p for p in produtos
        if p["tipo"] == "CDB"
        and p["prazo_dias"] <= PRAZO_CURTO_MAX_DIAS
    ]


def filtrar_isentos(produtos):
    return [
        p for p in produtos
        if p["tipo"] in {"LCI", "LCA"}
        and p["taxa"] >= ISENTO_MIN_CDI
    ]


def filtrar_selicplus(produtos):
    return [p for p in produtos if p["melhor_que_selic"]]

# -----------------------------
# ATUALIZAÇÃO
# -----------------------------

def atualizar_radar():
    try:
        produtos = extrair_produtos_yubb()
    except Exception:
        produtos = []

    estado["ranking"] = produtos[:10]
    estado["diarios"] = filtrar_diarios(produtos)[:10]
    estado["curtos"] = filtrar_curtos(produtos)[:10]
    estado["isentos"] = filtrar_isentos(produtos)[:10]
    estado["selicplus"] = filtrar_selicplus(produtos)[:10]
    estado["updated_at"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    salvar_estado()

# -----------------------------
# FORMATADORES
# -----------------------------

def formatar_lista(itens, titulo):
    if not itens:
        return f"{titulo}\n\nNenhuma oportunidade encontrada na fonte monitorada agora."

    texto = f"{titulo}\n\n"

    for i, item in enumerate(itens[:10], 1):
        texto += (
            f"{i}. {item['tipo']} | {item['emissor']}\n"
            f"{item['taxa']:.2f}% CDI\n"
            f"retorno líquido: {item['retorno_liquido']:.2f}%\n"
            f"score: {item['score']}\n"
            f"{item['classificacao']}\n\n"
        )

    return texto.strip()

# -----------------------------
# COMANDOS
# -----------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = """
💰 Radar de Investimentos

/menu
/status
/ranking
/diarios
/curtos
/isentos
/benchmark
/selicplus
"""
    await update.message.reply_text(texto)


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = """
📊 MENU

/status
/ranking
/diarios
/curtos
/isentos
/benchmark
/selicplus
"""
    await update.message.reply_text(texto)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not estado.get("updated_at"):
        atualizar_radar()

    texto = f"""
🟢 Radar online

Última atualização: {estado.get("updated_at", "não disponível")}
Diários no cache: {len(estado.get("diarios", []))}
Curtos no cache: {len(estado.get("curtos", []))}
Isentos no cache: {len(estado.get("isentos", []))}
Melhores que Selic: {len(estado.get("selicplus", []))}

Fontes monitoradas:
✔ Yubb
✔ benchmark Selic
✔ comparador líquido
✔ detector melhor que Selic
"""
    await update.message.reply_text(texto)


async def benchmark(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = f"""
🏦 Benchmark

Tesouro Selic

Taxa aproximada:
{SELIC:.2f}%
"""
    await update.message.reply_text(texto)


async def ranking_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    atualizar_radar()
    await update.message.reply_text(formatar_lista(estado.get("ranking", []), "🏆 Ranking de oportunidades"))


async def diarios_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    atualizar_radar()
    await update.message.reply_text(formatar_lista(estado.get("diarios", []), "💧 CDBs de liquidez diária"))


async def curtos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    atualizar_radar()
    await update.message.reply_text(formatar_lista(estado.get("curtos", []), "⏱ CDBs de prazo curto"))


async def isentos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    atualizar_radar()
    await update.message.reply_text(formatar_lista(estado.get("isentos", []), "🟢 LCI / LCA"))


async def selicplus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    atualizar_radar()
    await update.message.reply_text(formatar_lista(estado.get("selicplus", []), "🚨 Melhores que o Tesouro Selic"))

# -----------------------------
# MAIN
# -----------------------------

def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN não definido.")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("benchmark", benchmark))
    app.add_handler(CommandHandler("ranking", ranking_cmd))
    app.add_handler(CommandHandler("diarios", diarios_cmd))
    app.add_handler(CommandHandler("curtos", curtos_cmd))
    app.add_handler(CommandHandler("isentos", isentos_cmd))
    app.add_handler(CommandHandler("selicplus", selicplus_cmd))

    print("Radar de Investimentos iniciado")
    app.run_polling()


if __name__ == "__main__":
    main()
