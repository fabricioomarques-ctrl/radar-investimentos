import json
import os
from datetime import datetime

from telegram import ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler
import config
from engine import collect_all, get_source_status
from ranking import rank


ALERTS_SENT_FILE = "alerts_sent.json"
ALERT_RUNTIME_FILE = "alert_runtime.json"

ALERT_INTERVAL_SECONDS = getattr(config, "ALERT_INTERVAL_SECONDS", 1800)
MAX_ALERTS_PER_CYCLE = getattr(config, "MAX_ALERTS_PER_CYCLE", 3)

TELEGRAM_BOT_TOKEN = config.TELEGRAM_BOT_TOKEN
BOT_NAME = config.BOT_NAME
SELIC = config.SELIC
CDI = config.CDI


def load_json_file(path, default):
    if not os.path.exists(path):
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json_file(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_alert_cache():
    return load_json_file(
        ALERTS_SENT_FILE,
        {
            "sent_ids": [],
            "last_cleanup": datetime.now().strftime("%Y-%m-%d")
        }
    )


def save_alert_cache(cache):
    save_json_file(ALERTS_SENT_FILE, cache)


def cleanup_alert_cache(cache, max_size=2000):
    sent_ids = cache.get("sent_ids", [])

    if len(sent_ids) > max_size:
        cache["sent_ids"] = sent_ids[-max_size:]

    cache["last_cleanup"] = datetime.now().strftime("%Y-%m-%d")
    return cache


def load_alert_runtime():
    return load_json_file(
        ALERT_RUNTIME_FILE,
        {
            "alert_chat_id": None,
            "last_run": None,
            "last_total_ranked": 0,
            "last_candidates": 0,
            "last_sent_count": 0,
            "last_error": "",
            "last_alert_preview": ""
        }
    )


def save_alert_runtime(runtime_data):
    save_json_file(ALERT_RUNTIME_FILE, runtime_data)


def get_registered_alert_chat_id():
    runtime_data = load_alert_runtime()
    return runtime_data.get("alert_chat_id")


def set_registered_alert_chat_id(chat_id):
    runtime_data = load_alert_runtime()
    runtime_data["alert_chat_id"] = str(chat_id)
    save_alert_runtime(runtime_data)


def build_ranked_data():
    data = collect_all()
    ranked = rank(data)
    return ranked


def format_item(i, r):
    sim_label = "🧪 Dado de exemplo\n" if r.get("bank") == "Simulação Interna" else ""
    rare_label = "🔥 OPORTUNIDADE RARA\n" if r.get("rare") else ""
    selic_label = "✅ Melhor que Selic" if r.get("beats_selic") else "➖ Não supera a Selic"

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


def build_alert_id(r):
    return "|".join([
        str(r.get("bank", "")).strip().lower(),
        str(r.get("type", "")).strip().upper(),
        str(round(float(r.get("rate", 0)), 2)),
        str(int(r.get("days", 365))),
        str(bool(r.get("liquidity", False))),
    ])


def is_alert_candidate(r):
    return bool(r.get("beats_selic")) or bool(r.get("rare"))


def build_alert_message(r):
    rare_label = "🔥 OPORTUNIDADE RARA\n" if r.get("rare") else ""
    selic_label = "✅ Melhor que Selic\n" if r.get("beats_selic") else ""

    return (
        "🚨 OPORTUNIDADE DETECTADA\n\n"
        f"{rare_label}"
        f"💼 {r['type']} {r['rate']}% CDI\n"
        f"🏦 Instituição: {r['bank']}\n"
        f"📅 Prazo: {r['days']} dias\n"
        f"💧 Liquidez diária: {'Sim' if r['liquidity'] else 'Não'}\n"
        f"🧾 Retorno bruto estimado: {r['gross']:.2f}% a.a.\n"
        f"💰 Retorno líquido estimado: {r['net']:.2f}% a.a.\n"
        f"📊 Score: {r['score']}\n"
        f"{r['classification']}\n"
        f"{selic_label}"
    )


async def process_automatic_alerts(application):
    runtime_data = load_alert_runtime()

    try:
        chat_id = runtime_data.get("alert_chat_id")
        if not chat_id:
            runtime_data["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            runtime_data["last_error"] = "nenhum chat de alerta registrado"
            runtime_data["last_sent_count"] = 0
            save_alert_runtime(runtime_data)
            return

        ranked = build_ranked_data()
        candidates = [r for r in ranked if is_alert_candidate(r)]

        cache = load_alert_cache()
        sent_ids = set(cache.get("sent_ids", []))

        new_candidates = []
        for r in candidates:
            aid = build_alert_id(r)
            if aid not in sent_ids:
                new_candidates.append(r)

        new_candidates = new_candidates[:MAX_ALERTS_PER_CYCLE]

        sent_count = 0
        last_alert_preview = ""

        for r in new_candidates:
            msg = build_alert_message(r)
            await application.bot.send_message(chat_id=chat_id, text=msg)

            sent_ids.add(build_alert_id(r))
            sent_count += 1
            last_alert_preview = f"{r['type']} {r['rate']}% CDI | {r['bank']}"

        cache["sent_ids"] = list(sent_ids)
        cache = cleanup_alert_cache(cache)
        save_alert_cache(cache)

        runtime_data["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        runtime_data["last_total_ranked"] = len(ranked)
        runtime_data["last_candidates"] = len(candidates)
        runtime_data["last_sent_count"] = sent_count
        runtime_data["last_error"] = ""
        runtime_data["last_alert_preview"] = last_alert_preview
        save_alert_runtime(runtime_data)

    except Exception as e:
        runtime_data["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        runtime_data["last_error"] = str(e)
        runtime_data["last_sent_count"] = 0
        save_alert_runtime(runtime_data)


async def alert_job(context):
    await process_automatic_alerts(context.application)


async def post_init(application):
    if application.job_queue is None:
        print("⚠️ JobQueue não disponível. Alertas automáticos não serão agendados.")
        return

    application.job_queue.run_repeating(
        alert_job,
        interval=ALERT_INTERVAL_SECONDS,
        first=15,
        name="automatic_alert_job"
    )
    print(f"🟢 Job de alertas agendado a cada {ALERT_INTERVAL_SECONDS} segundos")


def register_current_chat(update):
    if update and update.effective_chat:
        set_registered_alert_chat_id(update.effective_chat.id)


async def start_cmd(update, context):
    register_current_chat(update)

    msg = (
        f"💰 {BOT_NAME}\n\n"
        "/menu - ver menu completo\n"
        "/ranking - ver ranking\n"
        "/top10 - top 10\n"
        "/diarios - CDB liquidez diária\n"
        "/curtos - CDB curto prazo\n"
        "/isentos - LCI/LCA\n"
        "/selicplus - melhores que Selic\n"
        "/benchmark - ver benchmark\n"
        "/status - ver status\n"
        "/alertastatus - status dos alertas\n"
        "/testealerta - enviar alerta de teste\n"
        "/setalertchat - registrar este chat para alertas automáticos"
    )

    await update.message.reply_text(
        msg,
        reply_markup=ReplyKeyboardRemove()
    )


async def menu_cmd(update, context):
    register_current_chat(update)

    msg = (
        f"💰 {BOT_NAME}\n\n"
        "/ranking - ver ranking\n"
        "/top10 - top 10\n"
        "/diarios - CDB liquidez diária\n"
        "/curtos - CDB curto prazo\n"
        "/isentos - LCI/LCA\n"
        "/selicplus - melhores que Selic\n"
        "/benchmark - ver benchmark\n"
        "/status - ver status\n"
        "/alertastatus - status dos alertas\n"
        "/testealerta - enviar alerta de teste\n"
        "/setalertchat - registrar este chat para alertas automáticos"
    )

    await update.message.reply_text(
        msg,
        reply_markup=ReplyKeyboardRemove()
    )


async def benchmark_cmd(update, context):
    register_current_chat(update)

    msg = (
        "🏦 Benchmark\n\n"
        f"Tesouro Selic: {SELIC:.2f}%\n"
        f"CDI: {CDI:.2f}%"
    )
    await update.message.reply_text(msg)


async def status_cmd(update, context):
    register_current_chat(update)

    ranked = build_ranked_data()
    source_status = get_source_status()

    real_count = sum(1 for i in ranked if i.get("bank") != "Simulação Interna")
    sim_count = sum(1 for i in ranked if i.get("bank") == "Simulação Interna")

    beats_selic = sum(1 for i in ranked if i.get("net", 0) > SELIC)
    diarios = sum(1 for i in ranked if i.get("type") == "CDB" and i.get("liquidity"))
    curtos = sum(1 for i in ranked if i.get("type") == "CDB" and i.get("days", 0) <= 365)
    isentos = sum(1 for i in ranked if i.get("type") in ["LCI", "LCA"])

    source_labels = {
        "yubb": "🔎 Yubb",
        "public_pages": "🌍 Páginas públicas",
        "investidor10": "📈 Investidor10",
        "maisretorno": "📊 MaisRetorno",
        "statusinvest": "📉 StatusInvest",
        "fallback": "🧪 Fallback",
    }

    active_sources = []
    inactive_sources = []
    fallback_line = None

    for source_name, info in source_status.items():
        label = source_labels.get(source_name, f"📌 {source_name}")
        count = info.get("count", 0)
        error = str(info.get("error", "")).strip()

        if source_name == "fallback":
            fallback_line = f"{label}: {count}"
            continue

        if count > 0:
            active_sources.append(f"{label}: {count}")
        else:
            if error:
                inactive_sources.append(f"{label} — {error[:120]}")
            else:
                inactive_sources.append(f"{label} — sem retorno no momento")

    active_sources_count = sum(
        1 for source_name, info in source_status.items()
        if source_name != "fallback" and info.get("count", 0) > 0
    )

    msg = (
        f"🟢 {BOT_NAME} online\n\n"
        f"📊 Oportunidades totais: {len(ranked)}\n"
        f"🌐 Oportunidades reais: {real_count}\n"
        f"📡 Fontes ativas: {active_sources_count}\n"
        f"🧪 Fallback/simulação: {sim_count}\n\n"
        f"🏦 Benchmark Selic: {SELIC:.2f}%\n"
        f"📈 CDI: {CDI:.2f}%\n\n"
        f"🚀 Melhores que Selic: {beats_selic}\n"
        f"💧 Liquidez diária: {diarios}\n"
        f"⏱ Curto prazo: {curtos}\n"
        f"🟢 Isentos (LCI/LCA): {isentos}\n\n"
    )

    if active_sources:
        msg += "✅ Fontes ativas\n"
        msg += "\n".join(active_sources)
        msg += "\n\n"

    if inactive_sources:
        msg += "⚠️ Fontes sem retorno no momento\n"
        msg += "\n".join(inactive_sources)
        msg += "\n\n"

    if fallback_line:
        msg += f"{fallback_line}"

    await update.message.reply_text(msg)


async def ranking_cmd(update, context):
    register_current_chat(update)

    ranked = build_ranked_data()

    msg = "🏆 Ranking de oportunidades\n\n"
    for i, r in enumerate(ranked[:10], 1):
        msg += format_item(i, r)

    await update.message.reply_text(msg)


async def top10_cmd(update, context):
    register_current_chat(update)

    ranked = build_ranked_data()

    msg = "🔝 Top 10 oportunidades\n\n"
    for i, r in enumerate(ranked[:10], 1):
        msg += format_item(i, r)

    await update.message.reply_text(msg)


async def diarios_cmd(update, context):
    register_current_chat(update)

    ranked = build_ranked_data()
    diarios = [r for r in ranked if r.get("type") == "CDB" and r.get("liquidity")]

    if not diarios:
        await update.message.reply_text("💧 Nenhuma oportunidade com liquidez diária encontrada nas fontes ativas no momento.")
        return

    msg = "💧 CDBs de liquidez diária\n\n"
    for i, r in enumerate(diarios[:10], 1):
        msg += format_item(i, r)

    await update.message.reply_text(msg)


async def curtos_cmd(update, context):
    register_current_chat(update)

    ranked = build_ranked_data()
    curtos = [r for r in ranked if r.get("type") == "CDB" and r.get("days", 0) <= 365]

    if not curtos:
        await update.message.reply_text("⏱ Nenhuma oportunidade de curto prazo encontrada nas fontes ativas no momento.")
        return

    msg = "⏱ CDBs de curto prazo\n\n"
    for i, r in enumerate(curtos[:10], 1):
        msg += format_item(i, r)

    await update.message.reply_text(msg)


async def isentos_cmd(update, context):
    register_current_chat(update)

    ranked = build_ranked_data()
    isentos = [r for r in ranked if r.get("type") in ["LCI", "LCA"]]

    if not isentos:
        await update.message.reply_text("🟢 Nenhum investimento isento encontrado nas fontes ativas no momento.")
        return

    msg = "🟢 LCI / LCA\n\n"
    for i, r in enumerate(isentos[:10], 1):
        msg += format_item(i, r)

    await update.message.reply_text(msg)


async def selicplus_cmd(update, context):
    register_current_chat(update)

    ranked = build_ranked_data()
    selicplus = [r for r in ranked if r.get("net", 0) > SELIC]

    if not selicplus:
        await update.message.reply_text("🚀 Nenhum investimento supera a Selic nas fontes ativas no momento.")
        return

    msg = "🚀 Melhores que a Selic\n\n"
    for i, r in enumerate(selicplus[:10], 1):
        msg += format_item(i, r)

    await update.message.reply_text(msg)


async def setalertchat_cmd(update, context):
    register_current_chat(update)
    chat_id = update.effective_chat.id

    msg = (
        "✅ Chat de alertas registrado com sucesso.\n\n"
        f"Chat ID atual: {chat_id}\n"
        f"Os alertas automáticos passarão a ser enviados aqui "
        f"a cada {ALERT_INTERVAL_SECONDS // 60} minutos."
    )
    await update.message.reply_text(msg)


async def alertastatus_cmd(update, context):
    register_current_chat(update)

    runtime_data = load_alert_runtime()
    cache = load_alert_cache()
    registered_chat_id = runtime_data.get("alert_chat_id")

    msg = (
        "🚨 Status dos alertas automáticos\n\n"
        f"📍 Chat registrado: {registered_chat_id or 'não definido'}\n"
        f"⏱ Intervalo: {ALERT_INTERVAL_SECONDS} segundos\n"
        f"📦 IDs no cache anti-repetição: {len(cache.get('sent_ids', []))}\n"
        f"🕒 Última execução: {runtime_data.get('last_run') or 'ainda não executou'}\n"
        f"📊 Último total ranqueado: {runtime_data.get('last_total_ranked', 0)}\n"
        f"🎯 Últimos candidatos: {runtime_data.get('last_candidates', 0)}\n"
        f"📨 Últimos alertas enviados: {runtime_data.get('last_sent_count', 0)}\n"
        f"🔔 Último alerta: {runtime_data.get('last_alert_preview') or 'nenhum'}"
    )

    if runtime_data.get("last_error"):
        msg += f"\n\n⚠️ Último erro: {runtime_data['last_error'][:250]}"

    await update.message.reply_text(msg)


async def testealerta_cmd(update, context):
    register_current_chat(update)

    sample = {
        "type": "CDB",
        "rate": 120,
        "bank": "Banco Teste",
        "days": 365,
        "liquidity": True,
        "gross": 12.78,
        "net": 10.90,
        "score": 9,
        "classification": "🔴 OPORTUNIDADE IMPERDÍVEL",
        "rare": True,
        "beats_selic": True,
    }

    msg = build_alert_message(sample)
    await update.message.reply_text(msg)


def main():
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("Defina TELEGRAM_BOT_TOKEN nas variáveis do Railway.")

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("menu", menu_cmd))
    app.add_handler(CommandHandler("benchmark", benchmark_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("ranking", ranking_cmd))
    app.add_handler(CommandHandler("top10", top10_cmd))
    app.add_handler(CommandHandler("diarios", diarios_cmd))
    app.add_handler(CommandHandler("curtos", curtos_cmd))
    app.add_handler(CommandHandler("isentos", isentos_cmd))
    app.add_handler(CommandHandler("selicplus", selicplus_cmd))
    app.add_handler(CommandHandler("setalertchat", setalertchat_cmd))
    app.add_handler(CommandHandler("alertastatus", alertastatus_cmd))
    app.add_handler(CommandHandler("testealerta", testealerta_cmd))

    print(f"🟢 {BOT_NAME} online")
    app.run_polling()


if __name__ == "__main__":
    main()
