from telegram.ext import Application, CommandHandler
from config import TELEGRAM_BOT_TOKEN, BOT_NAME, SELIC, CDI
from engine import collect_all
from ranking import rank


def build_ranked_data():
    data = collect_all()
    ranked = rank(data)
    return ranked


def format_item(i, r):
    sim_label = "🧪 Dado de exemplo\n" if r["bank"] == "Simulação Interna" else ""
    rare_label = "🔥 OPORTUNIDADE RARA\n" if r.get("rare") else ""
    selic_label = "✅ Melhor que Selic" if r["beats_selic"] else "➖ Não supera a Selic"

    msg = ""
    msg += f"{sim_label}{rare_label}{i}️⃣ {r['type']} {r['rate']}% CDI\n"
    msg += f"🏦 Instituição: {r['bank']}\n"
    msg += f"📅 Prazo: {r['days']} dias\n"
    msg += f"💧 Liquidez diária: {'Sim' if r['liquidity'] else 'Não'}\n"
    msg += f"🧾 Retorno bruto estimado: {r['gross']:.2f}% a.a.\n"
    msg += f"💰 Retorno líquido estimado: {r['net']:.2f}% a.a.\n"
    msg += f"📊 Score: {r['score']}\n"
    msg += f"{r['classification']}\n"
    msg += f"{selic_label}\n\n"
    return msg


async def start_cmd(update, context):
    msg = (
        f"💰 {BOT_NAME}\n\n"
        "/ranking - ver ranking\n"
        "/top10 - top 10\n"
        "/diarios - CDB liquidez diária\n"
        "/curtos - CDB curto prazo\n"
        "/isentos - LCI/LCA\n"
        "/selicplus - melhores que Selic\n"
        "/benchmark - ver benchmark\n"
        "/status - ver status"
    )
    await update.message.reply_text(msg)


async def benchmark_cmd(update, context):
    msg = (
        "🏦 Benchmark\n\n"
        f"Tesouro Selic: {SELIC:.2f}%\n"
        f"CDI: {CDI:.2f}%"
    )
    await update.message.reply_text(msg)


async def status_cmd(update, context):
    ranked = build_ranked_data()

    real_count = sum(1 for i in ranked if i["bank"] != "Simulação Interna")
    sim_count = sum(1 for i in ranked if i["bank"] == "Simulação Interna")

    beats_selic = sum(1 for i in ranked if i["net"] > SELIC)
    diarios = sum(1 for i in ranked if i["type"] == "CDB" and i["liquidity"])
    curtos = sum(1 for i in ranked if i["type"] == "CDB" and i["days"] <= 365)
    isentos = sum(1 for i in ranked if i["type"] in ["LCI", "LCA"])

    msg = (
        f"🟢 {BOT_NAME} online\n\n"
        f"📊 Total coletado: {len(ranked)}\n"
        f"🌐 Fontes reais: {real_count}\n"
        f"🧪 Fallback/simulação: {sim_count}\n\n"
        f"🏦 Benchmark Selic: {SELIC:.2f}%\n"
        f"📈 CDI: {CDI:.2f}%\n\n"
        f"🚀 Melhores que Selic: {beats_selic}\n"
        f"💧 Liquidez diária: {diarios}\n"
        f"⏱ Curto prazo: {curtos}\n"
        f"🟢 Isentos (LCI/LCA): {isentos}"
    )

    await update.message.reply_text(msg)


async def ranking_cmd(update, context):
    ranked = build_ranked_data()

    msg = "🏆 Ranking de oportunidades\n\n"
    for i, r in enumerate(ranked[:10], 1):
        msg += format_item(i, r)

    await update.message.reply_text(msg)


async def top10_cmd(update, context):
    ranked = build_ranked_data()

    msg = "🔝 Top 10 oportunidades\n\n"
    for i, r in enumerate(ranked[:10], 1):
        msg += format_item(i, r)

    await update.message.reply_text(msg)


async def diarios_cmd(update, context):
    ranked = build_ranked_data()
    diarios = [r for r in ranked if r["type"] == "CDB" and r["liquidity"]]

    if not diarios:
        await update.message.reply_text("💧 Nenhum CDB com liquidez diária encontrado.")
        return

    msg = "💧 CDBs de liquidez diária\n\n"
    for i, r in enumerate(diarios[:10], 1):
        msg += format_item(i, r)

    await update.message.reply_text(msg)


async def curtos_cmd(update, context):
    ranked = build_ranked_data()
    curtos = [r for r in ranked if r["type"] == "CDB" and r["days"] <= 365]

    if not curtos:
        await update.message.reply_text("⏱ Nenhum CDB de curto prazo encontrado.")
        return

    msg = "⏱ CDBs de curto prazo\n\n"
    for i, r in enumerate(curtos[:10], 1):
        msg += format_item(i, r)

    await update.message.reply_text(msg)


async def isentos_cmd(update, context):
    ranked = build_ranked_data()
    isentos = [r for r in ranked if r["type"] in ["LCI", "LCA"]]

    if not isentos:
        await update.message.reply_text("🟢 Nenhum investimento isento encontrado.")
        return

    msg = "🟢 LCI / LCA\n\n"
    for i, r in enumerate(isentos[:10], 1):
        msg += format_item(i, r)

    await update.message.reply_text(msg)


async def selicplus_cmd(update, context):
    ranked = build_ranked_data()
    selicplus = [r for r in ranked if r["net"] > SELIC]

    if not selicplus:
        await update.message.reply_text("🚀 Nenhum investimento supera a Selic no momento.")
        return

    msg = "🚀 Melhores que a Selic\n\n"
    for i, r in enumerate(selicplus[:10], 1):
        msg += format_item(i, r)

    await update.message.reply_text(msg)


def main():
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("Defina TELEGRAM_BOT_TOKEN nas variáveis do Railway.")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("benchmark", benchmark_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("ranking", ranking_cmd))
    app.add_handler(CommandHandler("top10", top10_cmd))
    app.add_handler(CommandHandler("diarios", diarios_cmd))
    app.add_handler(CommandHandler("curtos", curtos_cmd))
    app.add_handler(CommandHandler("isentos", isentos_cmd))
    app.add_handler(CommandHandler("selicplus", selicplus_cmd))

    app.run_polling()


if __name__ == "__main__":
    main()
