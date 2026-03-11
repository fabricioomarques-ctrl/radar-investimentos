from telegram.ext import Application, CommandHandler
from config import TELEGRAM_BOT_TOKEN, BOT_NAME, SELIC, CDI
from engine import collect_all, get_source_status
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
    source_status = get_source_status()

    real_count = sum(1 for i in ranked if i["bank"] != "Simulação Interna")
    sim_count = sum(1 for i in ranked if i["bank"] == "Simulação Interna")

    beats_selic = sum(1 for i in ranked if i["net"] > SELIC)
    diarios = sum(1 for i in ranked if i["type"] == "CDB" and i["liquidity"])
    curtos = sum(1 for i in ranked if i["type"] == "CDB" and i["days"] <= 365)
    isentos = sum(1 for i in ranked if i["type"] in ["LCI", "LCA"])

    yubb_status = source_status.get("yubb", {})
    public_status = source_status.get("public_pages", {})

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
        f"🟢 Isentos (LCI/LCA): {isentos}\n\n"
        f"🔎 Yubb: {yubb_status.get('count', 0)}\n"
        f"🌍 Páginas públicas: {public_status.get('count', 0)}"
    )

    if yubb_status.get("error"):
        msg += f"\n\n⚠️ Yubb: {yubb_status['error'][:180]}"

    if public_status.get("error"):
        msg += f"\n⚠️ Públicas: {public_status['error'][:180]}"

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
    diarios = [r for r in ranked if r["type"] ==
