import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from engine import collect_all
from ranking import rank
from config import TELEGRAM_TOKEN, BENCHMARK_SELIC, CDI_RATE


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
💰 Radar de Investimentos

/menu
/status
/ranking
/diarios
/curtos
/isentos
/benchmark
"""
    await update.message.reply_text(text)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):

    data = collect_all()

    ranked = rank(data)

    total = len(ranked)

    reais = len([r for r in ranked if r["source"] != "Simulação Interna"])

    simulados = len([r for r in ranked if r["source"] == "Simulação Interna"])

    melhores_selic = len([r for r in ranked if r["net"] > BENCHMARK_SELIC])

    diarios = len([r for r in ranked if r["liquidity"]])

    curtos = len([r for r in ranked if r["days"] <= 365])

    isentos = len([r for r in ranked if r["type"] in ["LCI", "LCA"]])

    text = f"""
🟢 Radar de Investimentos PRO MAX online

📊 Total coletado: {total}
🌐 Fontes reais: {reais}
🧪 Fallback/simulação: {simulados}

🏦 Benchmark Selic: {BENCHMARK_SELIC}%
📈 CDI: {CDI_RATE}%

🚀 Melhores que Selic: {melhores_selic}
💧 Liquidez diária: {diarios}
⏱ Curto prazo: {curtos}
🟢 Isentos (LCI/LCA): {isentos}
"""

    await update.message.reply_text(text)


async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):

    data = collect_all()

    ranked = rank(data)

    text = "🏆 Ranking de oportunidades\n\n"

    for i, r in enumerate(ranked[:10], start=1):

        tag = "🟢 BOA OPORTUNIDADE" if r["score"] >= 5 else "⚪ OPORTUNIDADE PADRÃO"

        supera = "🚀 Supera Selic" if r["net"] > BENCHMARK_SELIC else "➖ Não supera a Selic"

        text += f"""
{ i }️⃣ {r["type"]} {r["rate"]}% CDI
🏦 Instituição: {r["bank"]}
📅 Prazo: {r["days"]} dias
💧 Liquidez diária: {"Sim" if r["liquidity"] else "Não"}
🧾 Retorno bruto estimado: {r["gross"]:.2f}% a.a.
💰 Retorno líquido estimado: {r["net"]:.2f}% a.a.
📊 Score: {r["score"]}
{tag}
{supera}

"""

    await update.message.reply_text(text)


async def diarios(update: Update, context: ContextTypes.DEFAULT_TYPE):

    data = collect_all()

    ranked = rank(data)

    diarios = [r for r in ranked if r["liquidity"]]

    if not diarios:

        await update.message.reply_text(
            "💧 CDBs de liquidez diária\n\nNenhuma oportunidade encontrada na fonte monitorada agora."
        )
        return

    text = "💧 CDBs de liquidez diária\n\n"

    for i, r in enumerate(diarios[:10], start=1):

        text += f"""
{i}️⃣ {r["type"]} {r["rate"]}% CDI
🏦 {r["bank"]}
📅 {r["days"]} dias
💰 {r["net"]:.2f}% a.a.

"""

    await update.message.reply_text(text)


async def curtos(update: Update, context: ContextTypes.DEFAULT_TYPE):

    data = collect_all()

    ranked = rank(data)

    curtos = [r for r in ranked if r["days"] <= 365]

    if not curtos:

        await update.message.reply_text(
            "⏱ CDBs de prazo curto\n\nNenhuma oportunidade encontrada na fonte monitorada agora."
        )
        return

    text = "⏱ CDBs de prazo curto\n\n"

    for i, r in enumerate(curtos[:10], start=1):

        text += f"""
{i}️⃣ {r["type"]} {r["rate"]}% CDI
🏦 {r["bank"]}
📅 {r["days"]} dias
💰 {r["net"]:.2f}% a.a.

"""

    await update.message.reply_text(text)


async def isentos(update: Update, context: ContextTypes.DEFAULT_TYPE):

    data = collect_all()

    ranked = rank(data)

    isentos = [r for r in ranked if r["type"] in ["LCI", "LCA"]]

    if not isentos:

        await update.message.reply_text(
            "🟢 LCI / LCA\n\nNenhuma oportunidade encontrada na fonte monitorada agora."
        )
        return

    text = "🟢 LCI / LCA\n\n"

    for i, r in enumerate(isentos[:10], start=1):

        text += f"""
{i}️⃣ {r["type"]} {r["rate"]}% CDI
🏦 {r["bank"]}
📅 {r["days"]} dias
💰 {r["net"]:.2f}% a.a.

"""

    await update.message.reply_text(text)


async def benchmark(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = f"""
🏦 Benchmark

Tesouro Selic

Taxa aproximada:
{BENCHMARK_SELIC}%
"""

    await update.message.reply_text(text)


def main():

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("ranking", ranking))
    app.add_handler(CommandHandler("diarios", diarios))
    app.add_handler(CommandHandler("curtos", curtos))
    app.add_handler(CommandHandler("isentos", isentos))
    app.add_handler(CommandHandler("benchmark", benchmark))

    print("Bot rodando...")

    app.run_polling()


if __name__ == "__main__":
    main()
