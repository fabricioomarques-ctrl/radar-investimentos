import os
import re
import json
import math
import time
import requests
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

ARQUIVO_ESTADO = "estado_investimentos.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
        "Mobile/15E148 Safari/604.1"
    )
}

# ==========================================
# CONFIGURAÇÃO DO RADAR
# ==========================================

# Regras definidas por você
CDB_DIARIO_MIN_CDI = 100.0
PRAZO_CURTO_MAX_DIAS = 30

BANCOS_PRIORITARIOS = [
    "itaú",
    "itau",
    "c6",
    "bradesco",
    "nubank",
]

ACEITAR_OUTROS_COM_FGC = True

# Fontes
YUBB_RENDA_FIXA_URL = "https://yubb.com.br/investimentos/renda-fixa"

# SGS Bacen - SELIC anualizada base 252
BCB_SELIC_SERIE = 1178

# Intervalo de varredura
SCAN_INTERVAL = 1800  # 30 minutos

# Limites para alertas fortes
ALERTA_FORTE_CDB_DIARIO = 105.0
ALERTA_FORTE_CDB_CURTO = 108.0
ALERTA_FORTE_ISENTO = 95.0

# ==========================================
# ESTADO
# ==========================================

def estado_padrao():
    return {
        "sent": [],
        "benchmark": {},
        "cache": {
            "diarios": [],
            "curtos": [],
            "isentos": [],
            "ranking": [],
            "melhores_que_selic": [],
        },
        "updated_at": None,
    }


def carregar_estado():
    try:
        with open(ARQUIVO_ESTADO, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return estado_padrao()

        data.setdefault("sent", [])
        data.setdefault("benchmark", {})
        data.setdefault("cache", {
            "diarios": [],
            "curtos": [],
            "isentos": [],
            "ranking": [],
            "melhores_que_selic": [],
        })
        data.setdefault("updated_at", None)
        return data
    except Exception:
        return estado_padrao()


def salvar_estado():
    with open(ARQUIVO_ESTADO, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


estado = carregar_estado()

# ==========================================
# HELPERS
# ==========================================

def limpar_texto(texto: str) -> str:
    return re.sub(r"\s+", " ", (texto or "")).strip()


def normalizar(texto: str) -> str:
    return limpar_texto((texto or "").lower())


def parse_float_br(texto: str) -> float:
    if texto is None:
        return 0.0

    texto = str(texto).strip()

    # tenta formato brasileiro e simples
    try:
        return float(texto.replace(".", "").replace(",", "."))
    except Exception:
        try:
            return float(texto.replace(",", "."))
        except Exception:
            return 0.0


def formatar_data_br(data_obj: datetime) -> str:
    return data_obj.strftime("%d/%m/%Y")


def parse_data_br(texto: str):
    try:
        return datetime.strptime(texto, "%d/%m/%Y")
    except Exception:
        return None


def banco_prioritario(nome: str) -> bool:
    n = normalizar(nome)
    return any(b in n for b in BANCOS_PRIORITARIOS)


def ja_enviado(chave: str) -> bool:
    return chave in estado["sent"]


def registrar_envio(chave: str):
    if chave not in estado["sent"]:
        estado["sent"].append(chave)
        salvar_estado()


def slug_url(url: str) -> str:
    try:
        p = urlparse(url)
        return f"{p.netloc}{p.path}"
    except Exception:
        return url or ""


def score_classificacao(score: float) -> str:
    if score >= 9.0:
        return "🔴 Oportunidade forte"
    if score >= 7.5:
        return "🟡 Oportunidade muito boa"
    return "🟢 Oportunidade boa"

# ==========================================
# BENCHMARK - BACEN
# ==========================================

def buscar_selic_anualizada():
    data_final = datetime.today()
    data_inicial = data_final - timedelta(days=15)

    url = (
        f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{BCB_SELIC_SERIE}/dados"
        f"?formato=json&dataInicial={formatar_data_br(data_inicial)}&dataFinal={formatar_data_br(data_final)}"
    )

    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    dados = r.json()

    if not dados:
        return {
            "nome": "Tesouro Selic (benchmark)",
            "selic_anual": 0.0,
            "fonte": url,
            "data": "",
        }

    ultimo = dados[-1]
    valor = parse_float_br(ultimo.get("valor", "0"))
    data = ultimo.get("data", "")

    return {
        "nome": "Tesouro Selic (benchmark)",
        "selic_anual": valor,
        "fonte": url,
        "data": data,
    }

# ==========================================
# YUBB - COLETA
# ==========================================

def extrair_links_yubb(html: str):
    links = set()

    for href in re.findall(r'href="([^"]+)"', html):
        if "/investimentos/renda-fixa/" in href:
            full = urljoin(YUBB_RENDA_FIXA_URL, href)
            full = full.split("#")[0].split("?")[0]
            links.add(full)

    return list(links)


def detectar_tipo_produto(texto: str) -> str:
    txt = normalizar(texto)

    if " lci " in f" {txt} " or txt.startswith("lci"):
        return "LCI"

    if " lca " in f" {txt} " or txt.startswith("lca"):
        return "LCA"

    if " cdb " in f" {txt} " or txt.startswith("cdb"):
        return "CDB"

    return ""


def extrair_percentual_cdi(texto: str) -> float:
    m = re.search(r"(\d{2,3}(?:[.,]\d{1,2})?)\s*%\s*CDI", texto, flags=re.I)
    if not m:
        return 0.0
    return parse_float_br(m.group(1))


def extrair_minimo(texto: str) -> float:
    m = re.search(r"Investimento mínimo\s*R\$\s*([\d\.,]+)", texto, flags=re.I)
    if not m:
        return 0.0
    return parse_float_br(m.group(1))


def extrair_emissor(texto: str) -> str:
    m = re.search(
        r"Emissor\s+([A-Za-zÀ-ÿ0-9&\-\.\s]+?)(?:\s{2,}|Distribuidor|Prazo|Rentabilidade|Investimento|$)",
        texto,
        flags=re.I,
    )
    if not m:
        return ""
    return limpar_texto(m.group(1))


def extrair_distribuidor(texto: str) -> str:
    m = re.search(
        r"Distribuidor\s+([A-Za-zÀ-ÿ0-9&\-\.\s]+?)(?:\s{2,}|Emissor|Prazo|Rentabilidade|Investimento|$)",
        texto,
        flags=re.I,
    )
    if not m:
        return ""
    return limpar_texto(m.group(1))


def extrair_prazo_resgate(texto: str):
    m = re.search(r"Prazo de resgate\s*(\d{2}/\d{2}/\d{4})", texto, flags=re.I)
    if not m:
        return None
    return parse_data_br(m.group(1))


def liquidez_diaria(texto: str) -> bool:
    txt = normalizar(texto)
    return "liquidez diária" in txt or "liquidez diaria" in txt


def tem_fgc(texto: str) -> bool:
    return "fgc" in normalizar(texto)


def parse_pagina_produto(url: str):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    texto = limpar_texto(soup.get_text(" ", strip=True))

    tipo = detectar_tipo_produto(texto)
    if tipo not in {"CDB", "LCI", "LCA"}:
        return None

    taxa_cdi = extrair_percentual_cdi(texto)
    minimo = extrair_minimo(texto)
    emissor = extrair_emissor(texto)
    distribuidor = extrair_distribuidor(texto)
    vencimento = extrair_prazo_resgate(texto)
    diaria = liquidez_diaria(texto)
    fgc = tem_fgc(texto)

    titulo = ""
    if soup.title:
        titulo = limpar_texto(soup.title.get_text())
    if not titulo:
        h1 = soup.find("h1")
        if h1:
            titulo = limpar_texto(h1.get_text())
    if not titulo:
        titulo = slug_url(url)

    dias = None
    if vencimento:
        dias = (vencimento.date() - datetime.today().date()).days

    emissor_final = emissor or distribuidor or "Não identificado"

    return {
        "tipo": tipo,
        "titulo": titulo,
        "url": url,
        "taxa_cdi": taxa_cdi,
        "minimo": minimo,
        "emissor": emissor_final,
        "distribuidor": distribuidor,
        "fgc": fgc,
        "liquidez_diaria": diaria,
        "vencimento": vencimento.strftime("%d/%m/%Y") if vencimento else "",
        "dias_ate_vencimento": dias,
    }


def coletar_produtos_yubb(max_links: int = 60):
    r = requests.get(YUBB_RENDA_FIXA_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()

    links = extrair_links_yubb(r.text)
    produtos = []

    for url in links[:max_links]:
        try:
            item = parse_pagina_produto(url)
            if item:
                produtos.append(item)
        except Exception:
            continue

    return produtos

# ==========================================
# FILTROS
# ==========================================

def aceito_por_confianca(item: dict) -> bool:
    if banco_prioritario(item["emissor"]):
        return True
    return ACEITAR_OUTROS_COM_FGC and item.get("fgc", False)


def filtrar_diarios(produtos: list):
    saida = []
    for item in produtos:
        if item["tipo"] != "CDB":
            continue
        if not item["liquidez_diaria"]:
            continue
        if item["taxa_cdi"] < CDB_DIARIO_MIN_CDI:
            continue
        if not item["fgc"]:
            continue
        if not aceito_por_confianca(item):
            continue
        saida.append(item)
    return saida


def filtrar_curtos(produtos: list):
    saida = []
    for item in produtos:
        if item["tipo"] != "CDB":
            continue
        if not item["fgc"]:
            continue
        if not aceito_por_confianca(item):
            continue

        dias = item.get("dias_ate_vencimento")
        if dias is None:
            continue
        if dias < 0 or dias > PRAZO_CURTO_MAX_DIAS:
            continue

        saida.append(item)
    return saida


def filtrar_isentos(produtos: list):
    saida = []
    for item in produtos:
        if item["tipo"] not in {"LCI", "LCA"}:
            continue
        if not item["fgc"]:
            continue
        if not aceito_por_confianca(item):
            continue
        saida.append(item)
    return saida

# ==========================================
# COMPARAÇÃO LÍQUIDA
# ==========================================

def aliquota_ir(dias: int) -> float:
    if dias <= 180:
        return 0.225
    if dias <= 360:
        return 0.20
    if dias <= 720:
        return 0.175
    return 0.15


def retorno_bruto_anual(item: dict, selic_anual: float) -> float:
    # Aproximação simples: CDI ~ Selic para benchmark operacional
    # taxa_cdi = 105 -> 1.05 * CDI
    cdi_base = selic_anual / 100.0
    return cdi_base * (item.get("taxa_cdi", 0.0) / 100.0)


def retorno_liquido_anual(item: dict, selic_anual: float) -> float:
    bruto = retorno_bruto_anual(item, selic_anual)

    if item["tipo"] == "CDB":
        dias = item.get("dias_ate_vencimento") or 365
        ir = aliquota_ir(max(dias, 1))
        return bruto * (1 - ir)

    # LCI/LCA são isentas
    return bruto


def melhor_que_selic(item: dict, selic_anual: float) -> bool:
    selic = selic_anual / 100.0
    liquido = retorno_liquido_anual(item, selic_anual)
    return liquido > selic

# ==========================================
# SCORE E RANKING
# ==========================================

def score_item(item: dict, selic_anual: float) -> float:
    score = 0.0
    taxa = item.get("taxa_cdi", 0.0)

    if taxa > 105:
        score += 3
    elif taxa >= 100:
        score += 2

    if item.get("liquidez_diaria"):
        score += 2

    dias = item.get("dias_ate_vencimento")
    if dias is not None and 0 <= dias <= PRAZO_CURTO_MAX_DIAS:
        score += 2

    if banco_prioritario(item.get("emissor", "")):
        score += 2
    elif item.get("fgc"):
        score += 1

    minimo = item.get("minimo", 0.0)
    if minimo and minimo <= 1000:
        score += 1

    if item["tipo"] in {"LCI", "LCA"}:
        score += 0.5

    if melhor_que_selic(item, selic_anual):
        score += 1.0

    return round(min(score, 10.0), 1)


def enriquecer_item(item: dict, selic_anual: float):
    item2 = dict(item)
    item2["retorno_liquido_anual"] = round(retorno_liquido_anual(item2, selic_anual) * 100, 2)
    item2["melhor_que_selic"] = melhor_que_selic(item2, selic_anual)
    item2["score"] = score_item(item2, selic_anual)
    item2["classificacao"] = score_classificacao(item2["score"])
    return item2


def ordenar_com_score(lista: list, selic_anual: float):
    enriched = [enriquecer_item(item, selic_anual) for item in lista]

    return sorted(
        enriched,
        key=lambda x: (
            x["score"],
            x.get("melhor_que_selic", False),
            x.get("taxa_cdi", 0.0),
            -(x.get("minimo", 999999) or 999999),
        ),
        reverse=True,
    )

# ==========================================
# FORMATAÇÃO
# ==========================================

def fmt_produto(item: dict) -> str:
    linhas = [
        f"Produto: {item['tipo']}",
        f"Emissor: {item['emissor']}",
        f"Rentabilidade: {item['taxa_cdi']:.2f}% do CDI",
    ]

    if item.get("liquidez_diaria"):
        linhas.append("Liquidez: diária")

    if item.get("vencimento"):
        linhas.append(f"Vencimento: {item['vencimento']}")

    if item.get("dias_ate_vencimento") is not None:
        linhas.append(f"Dias até o vencimento: {item['dias_ate_vencimento']}")

    linhas.append(f"FGC: {'Sim' if item.get('fgc') else 'Não'}")

    if item.get("minimo"):
        linhas.append(f"Aplicação mínima: R$ {item['minimo']:.2f}")

    linhas.append(f"Retorno líquido anual estimado: {item['retorno_liquido_anual']:.2f}%")
    linhas.append(f"Melhor que Tesouro Selic: {'Sim' if item['melhor_que_selic'] else 'Não'}")
    linhas.append(f"Score: {item['score']}")
    linhas.append(item["classificacao"])
    linhas.append(f"Link: {item['url']}")

    return "\n".join(linhas)


def fmt_benchmark(benchmark: dict) -> str:
    return (
        "🏦 BENCHMARK DO RADAR\n\n"
        f"Produto: {benchmark.get('nome', 'Tesouro Selic')}\n"
        f"Selic anualizada: {benchmark.get('selic_anual', 0):.2f}% a.a.\n"
        f"Data da referência: {benchmark.get('data', '-')}\n"
        "Uso: referência para comparar alternativas privadas de caixa.\n"
        f"Fonte: {benchmark.get('fonte', '-')}"
    )

# ==========================================
# ALERTAS E CACHE
# ==========================================

async def enviar_privado(context, texto: str):
    await context.bot.send_message(chat_id=CHAT_ID, text=texto)


def atualizar_cache(diarios, curtos, isentos, ranking, benchmark, melhores_selic):
    estado["cache"]["diarios"] = diarios[:10]
    estado["cache"]["curtos"] = curtos[:10]
    estado["cache"]["isentos"] = isentos[:10]
    estado["cache"]["ranking"] = ranking[:10]
    estado["cache"]["melhores_que_selic"] = melhores_selic[:10]
    estado["benchmark"] = benchmark
    estado["updated_at"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    salvar_estado()


def chave_alerta(item: dict, sufixo: str = "") -> str:
    return f"{item['tipo']}|{slug_url(item['url'])}|{item['taxa_cdi']}|{sufixo}"


async def alertar_novidades(context, diarios, curtos, isentos, melhores_selic):
    candidatos = []
    candidatos.extend(diarios[:2])
    candidatos.extend(curtos[:2])
    candidatos.extend(isentos[:2])

    for item in candidatos:
        chave = chave_alerta(item)
        if ja_enviado(chave):
            continue

        emoji = "💰"
        if item["tipo"] in {"LCI", "LCA"}:
            emoji = "🏦"

        texto = f"{emoji} OPORTUNIDADE DE RENDA FIXA\n\n{fmt_produto(item)}"
        await enviar_privado(context, texto)
        registrar_envio(chave)

    # Alertas especiais: melhor que Selic
    for item in melhores_selic[:3]:
        chave = chave_alerta(item, "selic")
        if ja_enviado(chave):
            continue

        texto = (
            "🚨 MELHOR QUE TESOURO SELIC\n\n"
            f"{fmt_produto(item)}"
        )
        await enviar_privado(context, texto)
        registrar_envio(chave)

    # Alertas fortes
    for item in candidatos:
        taxa = item.get("taxa_cdi", 0.0)

        forte = False
        if item["tipo"] == "CDB" and item.get("liquidez_diaria") and taxa >= ALERTA_FORTE_CDB_DIARIO:
            forte = True
        elif item["tipo"] == "CDB" and (item.get("dias_ate_vencimento") or 9999) <= PRAZO_CURTO_MAX_DIAS and taxa >= ALERTA_FORTE_CDB_CURTO:
            forte = True
        elif item["tipo"] in {"LCI", "LCA"} and taxa >= ALERTA_FORTE_ISENTO:
            forte = True

        if not forte:
            continue

        chave = chave_alerta(item, "forte")
        if ja_enviado(chave):
            continue

        texto = (
            "🔥 OPORTUNIDADE FORTE\n\n"
            f"{fmt_produto(item)}"
        )
        await enviar_privado(context, texto)
        registrar_envio(chave)

# ==========================================
# COMANDOS
# ==========================================

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
📡 MENU

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
    texto = (
        "🟢 Radar online\n\n"
        f"Última atualização: {estado.get('updated_at') or 'ainda não executado'}\n"
        f"Diários no cache: {len(estado['cache'].get('diarios', []))}\n"
        f"Curtos no cache: {len(estado['cache'].get('curtos', []))}\n"
        f"Isentos no cache: {len(estado['cache'].get('isentos', []))}\n"
        f"Melhores que Selic: {len(estado['cache'].get('melhores_que_selic', []))}\n"
        "Detectores ativos:\n"
        "✔ benchmark Selic\n"
        "✔ CDB diário >= 100% CDI\n"
        "✔ CDB curto <= 30 dias\n"
        "✔ LCI/LCA com FGC\n"
        "✔ comparador líquido\n"
        "✔ melhor que Tesouro Selic\n"
        "✔ score automático\n"
        "✔ alerta privado"
    )
    await update.message.reply_text(texto)


async def benchmark_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bench = estado.get("benchmark", {})
    if not bench:
        await update.message.reply_text("Benchmark ainda não carregado.")
        return
    await update.message.reply_text(fmt_benchmark(bench))


async def diarios_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    itens = estado["cache"].get("diarios", [])
    if not itens:
        await update.message.reply_text("Nenhum CDB diário encontrado no cache.")
        return

    partes = ["💧 Melhores CDBs de liquidez diária\n"]
    for i, item in enumerate(itens[:5], 1):
        partes.append(
            f"{i}. {item['emissor']} | {item['taxa_cdi']:.2f}% CDI | "
            f"mín. R$ {item.get('minimo', 0):.2f} | "
            f"liq. {item['retorno_liquido_anual']:.2f}% | score {item['score']}"
        )

    await update.message.reply_text("\n".join(partes))


async def curtos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    itens = estado["cache"].get("curtos", [])
    if not itens:
        await update.message.reply_text("Nenhum CDB curto encontrado no cache.")
        return

    partes = ["📅 Melhores CDBs até 30 dias\n"]
    for i, item in enumerate(itens[:5], 1):
        partes.append(
            f"{i}. {item['emissor']} | {item['taxa_cdi']:.2f}% CDI | "
            f"{item.get('dias_ate_vencimento')} dias | "
            f"liq. {item['retorno_liquido_anual']:.2f}% | score {item['score']}"
        )

    await update.message.reply_text("\n".join(partes))


async def isentos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    itens = estado["cache"].get("isentos", [])
    if not itens:
        await update.message.reply_text("Nenhuma LCI/LCA encontrada no cache.")
        return

    partes = ["🏦 Melhores isentos (LCI/LCA)\n"]
    for i, item in enumerate(itens[:5], 1):
        partes.append(
            f"{i}. {item['tipo']} | {item['emissor']} | {item['taxa_cdi']:.2f}% CDI | "
            f"liq. {item['retorno_liquido_anual']:.2f}% | score {item['score']}"
        )

    await update.message.reply_text("\n".join(partes))


async def ranking_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    itens = estado["cache"].get("ranking", [])
    if not itens:
        await update.message.reply_text("Nenhuma oportunidade ranqueada ainda.")
        return

    partes = ["🏆 Ranking de oportunidades\n"]
    for i, item in enumerate(itens[:10], 1):
        partes.append(
            f"{i}. {item['tipo']} | {item['emissor']} | "
            f"{item['taxa_cdi']:.2f}% CDI | "
            f"liq. {item['retorno_liquido_anual']:.2f}% | "
            f"score {item['score']}"
        )

    await update.message.reply_text("\n".join(partes))


async def selicplus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    itens = estado["cache"].get("melhores_que_selic", [])
    if not itens:
        await update.message.reply_text("Nenhuma oportunidade melhor que o Tesouro Selic no cache.")
        return

    partes = ["🚨 Melhores que o Tesouro Selic\n"]
    for i, item in enumerate(itens[:10], 1):
        partes.append(
            f"{i}. {item['tipo']} | {item['emissor']} | "
            f"{item['taxa_cdi']:.2f}% CDI | "
            f"liq. {item['retorno_liquido_anual']:.2f}% | "
            f"score {item['score']}"
        )

    await update.message.reply_text("\n".join(partes))

# ==========================================
# CICLO PRINCIPAL
# ==========================================

async def scan_investimentos(context):
    try:
        benchmark = buscar_selic_anualizada()
        selic_anual = benchmark.get("selic_anual", 0.0)
    except Exception:
        benchmark = {
            "nome": "Tesouro Selic (benchmark)",
            "selic_anual": 0.0,
            "data": "",
            "fonte": "",
        }
        selic_anual = 0.0

    try:
        produtos = coletar_produtos_yubb(max_links=60)
    except Exception:
        produtos = []

    diarios = ordenar_com_score(filtrar_diarios(produtos), selic_anual)
    curtos = ordenar_com_score(filtrar_curtos(produtos), selic_anual)
    isentos = ordenar_com_score(filtrar_isentos(produtos), selic_anual)

    combinados = diarios[:5] + curtos[:5] + isentos[:5]
    ranking = ordenar_com_score(combinados, selic_anual)

    melhores_selic = [item for item in ranking if item.get("melhor_que_selic")]
    melhores_selic = sorted(melhores_selic, key=lambda x: x["score"], reverse=True)

    atualizar_cache(diarios, curtos, isentos, ranking, benchmark, melhores_selic)
    await alertar_novidades(context, diarios, curtos, isentos, melhores_selic)

# ==========================================
# MAIN
# ==========================================

def main():
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("Defina TELEGRAM_TOKEN e CHAT_ID nas variáveis de ambiente.")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("benchmark", benchmark_cmd))
    app.add_handler(CommandHandler("diarios", diarios_cmd))
    app.add_handler(CommandHandler("curtos", curtos_cmd))
    app.add_handler(CommandHandler("isentos", isentos_cmd))
    app.add_handler(CommandHandler("ranking", ranking_cmd))
    app.add_handler(CommandHandler("selicplus", selicplus_cmd))

    job = app.job_queue
    job.run_repeating(scan_investimentos, interval=SCAN_INTERVAL, first=15)

    print("Radar de Investimentos PRO iniciado")
    app.run_polling()


if __name__ == "__main__":
    main()
