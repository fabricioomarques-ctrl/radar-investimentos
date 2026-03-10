import os
import requests
import re
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from bs4 import BeautifulSoup

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

YUBB_URL = "https://yubb.com.br/investimentos/renda-fixa"

# CDI aproximado atual
CDI = 0.1325

# SELIC benchmark
SELIC = 0.1075

HEADERS = {
"User-Agent":"Mozilla/5.0"
}

# -----------------------------------------
# BENCHMARK
# -----------------------------------------

def retorno_liquido(taxa_cdi, tipo):

    rendimento = CDI * (taxa_cdi/100)

    if tipo == "CDB":

        ir = 0.20
        rendimento = rendimento * (1-ir)

    return rendimento * 100

# -----------------------------------------
# SCORE
# -----------------------------------------

def calcular_score(item):

    score = 0

    if item["taxa"] >= 105:
        score += 3

    if item["tipo"] in ["LCI","LCA"]:
        score += 2

    if item["taxa"] >= 110:
        score += 2

    if item["fgc"]:
        score += 2

    return score

# -----------------------------------------
# LIMPAR TEXTO BANCO
# -----------------------------------------

def limpar_banco(texto):

    texto = texto.split("É a instituição")[0]
    texto = texto.split("é a instituição")[0]

    return texto.strip()

# -----------------------------------------
# COLETAR YUBB
# -----------------------------------------

def coletar_yubb():

    r = requests.get(YUBB_URL,headers=HEADERS)

    soup = BeautifulSoup(r.text,"html.parser")

    texto = soup.get_text()

    resultados = []

    blocos = re.findall(r'(LCI|LCA|CDB).*?(\d{2,3}\.\d+)% CDI',texto)

    for tipo,taxa in blocos:

        taxa = float(taxa)

        banco = "Banco"

        resultados.append({
        "tipo":tipo,
        "banco":banco,
        "taxa":taxa,
        "fgc":True
        })

    return resultados

# -----------------------------------------
# RANKING
# -----------------------------------------

def ranking():

    investimentos = coletar_yubb()

    lista = []

    for inv in investimentos:

        liquido = retorno_liquido(inv["taxa"],inv["tipo"])

        score = calcular_score(inv)

        inv["liquido"] = liquido
        inv["score"] = score

        lista.append(inv)

    lista.sort(key=lambda x:x["score"],reverse=True)

    return lista[:10]

# -----------------------------------------
# COMANDOS
# -----------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    texto = """
💰 Radar de Investimentos

/menu
/status
/ranking
/benchmark
"""

    await update.message.reply_text(texto)

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):

    texto = """
📊 MENU

/status
/ranking
/benchmark
"""

    await update.message.reply_text(texto)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):

    texto = """
🟢 Radar online

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
{SELIC*100:.2f}%
"""

    await update.message.reply_text(texto)

async def ranking_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    lista = ranking()

    texto = "🏆 Ranking de oportunidades\n\n"

    pos = 1

    for inv in lista:

        texto += f"""{pos}. {inv["tipo"]} | {inv["banco"]}
{inv["taxa"]:.2f}% CDI
retorno líquido: {inv["liquido"]:.2f}%
score: {inv["score"]}

"""

        pos += 1

    await update.message.reply_text(texto)

# -----------------------------------------
# MAIN
# -----------------------------------------

def main():

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("menu",menu))
    app.add_handler(CommandHandler("status",status))
    app.add_handler(CommandHandler("benchmark",benchmark))
    app.add_handler(CommandHandler("ranking",ranking_cmd))

    print("Radar Investimentos iniciado")

    app.run_polling()

if __name__ == "__main__":
    main()
