import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# -----------------------------
# CONFIGURAÇÕES
# -----------------------------

CDI = 0.1325  # exemplo 13.25%
SELIC = 0.1075  # exemplo 10.75%

IR_TABELA = {
    "ate_180": 0.225,
    "ate_360": 0.20,
    "ate_720": 0.175,
    "acima_720": 0.15
}

# -----------------------------
# DADOS SIMULADOS DE MERCADO
# (depois podemos conectar APIs)
# -----------------------------

INVESTIMENTOS = [

{
"tipo":"CDB",
"banco":"Banco Inter",
"cdi":1.05,
"prazo":30,
"liquidez":"diaria",
"fgc":True
},

{
"tipo":"CDB",
"banco":"C6 Bank",
"cdi":1.10,
"prazo":30,
"liquidez":"vencimento",
"fgc":True
},

{
"tipo":"LCI",
"banco":"Itaú",
"cdi":0.92,
"prazo":90,
"liquidez":"vencimento",
"fgc":True
},

{
"tipo":"LCA",
"banco":"Bradesco",
"cdi":0.95,
"prazo":120,
"liquidez":"vencimento",
"fgc":True
}

]

# -----------------------------
# FUNÇÕES
# -----------------------------

def calcular_ir(prazo):

    if prazo <= 180:
        return IR_TABELA["ate_180"]

    if prazo <= 360:
        return IR_TABELA["ate_360"]

    if prazo <= 720:
        return IR_TABELA["ate_720"]

    return IR_TABELA["acima_720"]


def rendimento_liquido(inv):

    rendimento = CDI * inv["cdi"]

    if inv["tipo"] == "CDB":

        ir = calcular_ir(inv["prazo"])
        rendimento = rendimento * (1-ir)

    return rendimento


def score(inv):

    s = 0

    if inv["cdi"] >= 1.05:
        s += 3

    if inv["liquidez"] == "diaria":
        s += 2

    if inv["prazo"] <= 30:
        s += 2

    if inv["fgc"]:
        s += 2

    return s


def melhores_investimentos():

    lista = []

    for inv in INVESTIMENTOS:

        liquido = rendimento_liquido(inv)

        lista.append({
        "tipo":inv["tipo"],
        "banco":inv["banco"],
        "cdi":inv["cdi"],
        "prazo":inv["prazo"],
        "liquido":liquido,
        "score":score(inv)
        })

    lista.sort(key=lambda x:x["score"],reverse=True)

    return lista


def melhores_que_selic():

    oportunidades = []

    for inv in INVESTIMENTOS:

        liquido = rendimento_liquido(inv)

        if liquido > SELIC:

            oportunidades.append(inv)

    return oportunidades

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
"""

    await update.message.reply_text(texto)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):

    texto = f"""
🟢 Radar online

Benchmark Selic: {SELIC*100:.2f}%

Fontes monitoradas: 8
"""

    await update.message.reply_text(texto)


async def benchmark(update: Update, context: ContextTypes.DEFAULT_TYPE):

    texto = f"""
📉 Benchmark

Tesouro Selic

Taxa atual aproximada:
{SELIC*100:.2f}%
"""

    await update.message.reply_text(texto)


async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):

    lista = melhores_investimentos()

    texto = "🏆 Ranking investimentos\n\n"

    pos = 1

    for inv in lista:

        texto += f"""{pos}️⃣ {inv["tipo"]} - {inv["banco"]}
CDI: {inv["cdi"]*100:.0f}%
Prazo: {inv["prazo"]} dias
Score: {inv["score"]}

"""

        pos += 1

    await update.message.reply_text(texto)


async def diarios(update: Update, context: ContextTypes.DEFAULT_TYPE):

    texto = "💧 Liquidez diária\n\n"

    for inv in INVESTIMENTOS:

        if inv["liquidez"] == "diaria":

            texto += f"""{inv["tipo"]} {inv["banco"]}
{inv["cdi"]*100:.0f}% CDI
\n"""

    await update.message.reply_text(texto)


async def curtos(update: Update, context: ContextTypes.DEFAULT_TYPE):

    texto = "⏱ Prazo curto\n\n"

    for inv in INVESTIMENTOS:

        if inv["prazo"] <= 30:

            texto += f"""{inv["tipo"]} {inv["banco"]}
{inv["cdi"]*100:.0f}% CDI
\n"""

    await update.message.reply_text(texto)


async def isentos(update: Update, context: ContextTypes.DEFAULT_TYPE):

    texto = "🟢 Investimentos isentos\n\n"

    for inv in INVESTIMENTOS:

        if inv["tipo"] in ["LCI","LCA"]:

            texto += f"""{inv["tipo"]} {inv["banco"]}
{inv["cdi"]*100:.0f}% CDI
\n"""

    await update.message.reply_text(texto)

# -----------------------------
# MAIN
# -----------------------------

def main():

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("menu",menu))
    app.add_handler(CommandHandler("status",status))
    app.add_handler(CommandHandler("ranking",ranking))
    app.add_handler(CommandHandler("diarios",diarios))
    app.add_handler(CommandHandler("curtos",curtos))
    app.add_handler(CommandHandler("isentos",isentos))
    app.add_handler(CommandHandler("benchmark",benchmark))

    print("Radar Investimentos iniciado")

    app.run_polling()


if __name__ == "__main__":
    main()
