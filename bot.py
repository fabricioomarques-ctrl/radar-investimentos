from telegram.ext import Application, CommandHandler
from config import TELEGRAM_BOT_TOKEN, BOT_NAME, SELIC, CDI
from engine import collect_all
from ranking import rank


async def start_cmd(update, context):
    msg = (
        f"💰 {BOT_NAME}\n\n"
        "/ranking - ver ranking\n"
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
    data = collect_all()

    real_count = sum(1 for item in data if item["bank"] != "Simulação Interna")
    sim_count = sum(1 for item in data if item["bank"] == "Simulação Interna")

    msg = (
        f"🟢 {BOT_NAME} online\n\n"
        f"Total coletado: {len(data)}\n"
        f"Fontes reais: {real_count}\n"
        f"Fallback/simulação: {sim_count}\n"
        f"Benchmark Selic: {SELIC:.2f}%\n"
        f"CDI: {CDI:.2f}%"
    )
    await update.message.reply_text(msg)


async def ranking_cmd(update, context):
    data = collect_all()
    ranked = rank(data)

    msg = "🏆 Ranking de oportunidades\n\n"

    for i, r in enumerate(ranked[:10], 1):
        sim_label = "🧪 Dado de exemplo\n" if r["bank"] == "Simulação Interna" else ""
        rare_label = "🔥 OPORTUNIDADE RARA\n" if r.get("rare") else ""
        selic_label = "✅ Melhor que Selic" if r["beats_selic"] else "➖ Não supera a Selic"

        msg += f"{sim_label}{rare_label}{i}️⃣ {r['type']} {r['rate']}% CDI\n"
        msg += f"🏦 Instituição: {r['bank']}\n"
        msg += f"📅 Prazo: {r['days']} dias\n"
        msg += f"💧 Liquidez diária: {'Sim' if r['liquidity'] else 'Não'}\n"
        msg += f"🧾 Retorno bruto estimado: {r['gross']:.2f}% a.a.\n"
        msg += f"💰 Retorno líquido estimado: {r['net']:.2f}% a.a.\n"
        msg += f"📊 Score: {r['score']}\n"
        msg += f"{r['classification']}\n"
        msg += f"{selic_label}\n\n"

    await update.message.reply_text(msg)


def main():
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("Defina TELEGRAM_BOT_TOKEN nas variáveis do Railway.")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("benchmark", benchmark_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("ranking", ranking_cmd))

    app.run_polling()


if __name__ == "__main__":
    main()
