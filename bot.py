import json
import os
import re
import unicodedata
from datetime import datetime

from telegram import ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler

import config
from engine import collect_all, get_source_status
from ranking import rank


ALERTS_SENT_FILE = "alerts_sent.json"
ALERT_RUNTIME_FILE = "alert_runtime.json"
RADAR_MARKET_FILE = "radar_market_state.json"

ALERT_INTERVAL_SECONDS = getattr(config, "ALERT_INTERVAL_SECONDS", 1800)
MAX_ALERTS_PER_CYCLE = getattr(config, "MAX_ALERTS_PER_CYCLE", 3)

TELEGRAM_BOT_TOKEN = config.TELEGRAM_BOT_TOKEN
BOT_NAME = config.BOT_NAME
SELIC = config.SELIC
CDI = config.CDI


# =========================================================
# JSON HELPERS
# =========================================================

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


# =========================================================
# ALERT CACHE / RUNTIME
# =========================================================

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


def set_registered_alert_chat_id(chat_id):
    runtime_data = load_alert_runtime()
    runtime_data["alert_chat_id"] = str(chat_id)
    save_alert_runtime(runtime_data)


# =========================================================
# RADAR MARKET STATE
# =========================================================

def load_market_state():
    return load_json_file(
        RADAR_MARKET_FILE,
        {
            "products": {},
            "events": [],
            "last_scan": None
        }
    )


def save_market_state(state):
    save_json_file(RADAR_MARKET_FILE, state)


def slugify_text(text):
    text = str(text or "").strip().lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "produto"


def normalize_bank_name(bank):
    bank = str(bank or "").strip().lower()

    aliases = {
        "banco inter": "inter",
        "inter": "inter",
        "banco pan": "pan",
        "pan": "pan",
        "mercado pago": "mercadopago",
        "mercadopago": "mercadopago",
        "mercado": "mercado",
    }

    return aliases.get(bank, bank)


def normalize_product_identity(inv_type):
    text = str(inv_type or "").strip()
    lower = text.lower()

    if lower == "lci" or lower.startswith("lci "):
        return "LCI"

    if lower == "lca" or lower.startswith("lca "):
        return "LCA"

    if lower == "cdb" or lower.startswith("cdb "):
        return "CDB"

    return slugify_text(text)


def normalize_liquidity_flag(value):
    return bool(value)


def build_product_key(r):
    bank = normalize_bank_name(r.get("bank"))
    product_identity = normalize_product_identity(r.get("type"))
    liquidity = normalize_liquidity_flag(r.get("liquidity"))

    return "|".join([
        bank,
        product_identity,
        str(liquidity),
    ])


def build_alert_id(r):
    return "|".join([
        str(r.get("bank", "")).strip().lower(),
        str(r.get("type", "")).strip().upper(),
        str(round(float(r.get("rate", 0)), 2)),
        str(int(r.get("days", 365))),
        str(bool(r.get("liquidity", False))),
    ])


def snapshot_from_item(r):
    return {
        "bank": r.get("bank"),
        "type": r.get("type"),
        "rate": r.get("rate"),
        "days": r.get("days"),
        "liquidity": r.get("liquidity"),
        "gross": r.get("gross"),
        "net": r.get("net"),
        "score": r.get("score"),
        "classification": r.get("classification"),
        "rare": r.get("rare"),
        "best_rate": r.get("best_rate"),
        "beats_selic": r.get("beats_selic"),
    }


def append_market_event(state, event, max_events=200):
    events = state.get("events", [])
    events.append(event)

    if len(events) > max_events:
        events = events[-max_events:]

    state["events"] = events


def scan_market_changes(ranked):
    state = load_market_state()
    old_products = state.get("products", {})
    new_products = {}

    new_items = []
    changed_items = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for r in ranked:
        product_key = build_product_key(r)
        current_snapshot = snapshot_from_item(r)
        current_snapshot["last_seen"] = now_str

        previous = old_products.get(product_key)

        if previous is None:
            new_items.append(r)
            append_market_event(
                state,
                {
                    "kind": "new",
                    "timestamp": now_str,
                    "product_key": product_key,
                    "item": current_snapshot,
                }
            )
        else:
            old_rate = previous.get("rate")
            new_rate = current_snapshot.get("rate")

            if old_rate != new_rate:
                changed_items.append({
                    "old": previous,
                    "new": current_snapshot,
                    "product_key": product_key
                })

                append_market_event(
                    state,
                    {
                        "kind": "rate_change",
                        "timestamp": now_str,
                        "product_key": product_key,
                        "old_rate": old_rate,
                        "new_rate": new_rate,
                        "item": current_snapshot,
                    }
                )

        new_products[product_key] = current_snapshot

    state["products"] = new_products
    state["last_scan"] = now_str
    save_market_state(state)

    return new_items, changed_items


# =========================================================
# RADAR DATA
# =========================================================

def build_ranked_data():
    data = collect_all()
    ranked = rank(data)
    return ranked


def format_item(i, r):

    rare_label = ""
    anomaly_label = ""
    best_label = ""

    if r.get("best_rate"):
        best_label = "🏆 MELHOR TAXA DO MERCADO\n"

    if r.get("rare"):
        rare_label = "🔥 OPORTUNIDADE RARA\n"

    if r.get("anomaly"):
        anomaly_label = "🚨 TAXA FORA DA CURVA\n"

    selic_label = (
        "✅ Melhor que Selic"
        if r.get("beats_selic")
        else "➖ Não supera a Selic"
    )

    msg = ""

    msg += best_label
    msg += rare_label
    msg += anomaly_label

    msg += f"{i}️⃣ {r['type']} {r['rate']}% CDI\n"

    msg += f"🏦 Instituição: {r['bank']}\n"

    msg += f"📅 Prazo: {r['days']} dias\n"

    msg += f"💧 Liquidez diária: {'Sim' if r['liquidity'] else 'Não'}\n"

    msg += f"🧾 Retorno bruto estimado: {r['gross']:.2f}% a.a.\n"

    msg += f"💰 Retorno líquido estimado: {r['net']:.2f}% a.a.\n"

    msg += f"📊 Score: {r['score']}\n"

    msg += f"{r['classification']}\n"

    msg += f"{selic_label}\n\n"

    return msg

def format_change_item(i, change):
    old_item = change["old"]
    new_item = change["new"]

    old_rate = old_item.get("rate")
    new_rate = new_item.get("rate")

    direction = "📈 TAXA MELHOROU" if new_rate > old_rate else "📉 TAXA PIOROU"

    return (
        f"{i}️⃣ {direction}\n"
        f"💼 {new_item.get('type')}\n"
        f"🏦 Instituição: {new_item.get('bank')}\n"
        f"📅 Prazo: {new_item.get('days')} dias\n"
        f"💧 Liquidez diária: {'Sim' if new_item.get('liquidity') else 'Não'}\n"
        f"🔁 Antes: {old_rate}% CDI\n"
        f"✨ Agora: {new_rate}% CDI\n\n"
    )


def build_best_rate_text():
    ranked = build_ranked_data()

    if not ranked:
        return "🏆 Nenhuma oportunidade disponível no radar no momento."

    best_rate = max(r["rate"] for r in ranked)
    best_items = [r for r in ranked if r["rate"] == best_rate]

    msg = "🏆 Melhores taxas do radar no momento\n\n"

    for i, r in enumerate(best_items, 1):
        msg += format_item(i, r)

    return msg.strip()


def build_real_rare_text():
    ranked = build_ranked_data()
    rare_items = [r for r in ranked if r.get("rare")]

    if not rare_items:
        return (
            "🔥 Nenhuma oportunidade rara real detectada no momento.\n\n"
            "O radar não encontrou taxa fora do padrão de mercado nesta rodada."
        )

    msg = "🔥 Oportunidades raras reais detectadas\n\n"

    for i, r in enumerate(rare_items[:10], 1):
        msg += format_item(i, r)

    return msg.strip()


# =========================================================
# ALERT LOGIC
# =========================================================

def is_alert_candidate(r):
    return bool(r.get("beats_selic")) or bool(r.get("rare")) or bool(r.get("best_rate"))


def build_alert_message(r):
    rare_label = "🔥 OPORTUNIDADE RARA REAL\n" if r.get("rare") else ""
    best_label = "🏆 MELHOR TAXA DO MERCADO\n" if r.get("best_rate") else ""
    selic_label = "✅ Melhor que Selic\n" if r.get("beats_selic") else ""

    return (
        "🚨 OPORTUNIDADE DETECTADA\n\n"
        f"{rare_label}"
        f"{best_label}"
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


# =========================================================
# UI TEXT BUILDERS
# =========================================================

def register_current_chat(update):
    if update and update.effective_chat:
        set_registered_alert_chat_id(update.effective_chat.id)


def build_main_menu_text():
    return (
        f"💰 {BOT_NAME}\n\n"
        "📚 Comandos principais\n"
        "/menu - ver menu completo\n"
        "/help - ajuda rápida do radar\n"
        "/about - sobre o radar\n"
        "/fontes - fontes monitoradas\n"
        "/stats - estatísticas do radar\n"
        "/novas - novas oportunidades\n"
        "/mudancas - mudanças de taxa\n"
        "/historico - histórico do radar\n"
        "/raras - oportunidades raras reais\n"
        "/melhortaxa - melhor taxa do radar\n"
        "/ranking - ver ranking\n"
        "/top10 - top 10\n"
        "/status - ver status\n"
        "/benchmark - ver benchmark\n\n"
        "📊 Filtros de oportunidades\n"
        "/diarios - CDB liquidez diária\n"
        "/curtos - CDB curto prazo\n"
        "/isentos - LCI/LCA\n"
        "/selicplus - melhores que Selic\n\n"
        "🚨 Alertas e sistema\n"
        "/alertastatus - status dos alertas\n"
        "/testealerta - enviar alerta de teste\n"
        "/setalertchat - registrar este chat para alertas automáticos"
    )


def build_help_text():
    return (
        f"📚 Ajuda do {BOT_NAME}\n\n"
        "Este bot monitora oportunidades de renda fixa e organiza os resultados automaticamente.\n\n"
        "📈 Análise geral\n"
        "/ranking - ranking principal das oportunidades\n"
        "/top10 - top 10 investimentos do radar\n"
        "/status - situação atual do radar e das fontes\n"
        "/fontes - mostra as fontes monitoradas\n"
        "/stats - mostra as estatísticas do radar\n"
        "/novas - mostra oportunidades novas detectadas\n"
        "/mudancas - mostra mudanças de taxa detectadas\n"
        "/historico - mostra os últimos eventos do radar\n"
        "/raras - mostra oportunidades raras reais\n"
        "/melhortaxa - mostra a melhor taxa atual do radar\n"
        "/benchmark - Selic e CDI atuais usados na comparação\n\n"
        "🔎 Filtros específicos\n"
        "/diarios - oportunidades com liquidez diária\n"
        "/curtos - investimentos de curto prazo\n"
        "/isentos - LCIs e LCAs\n"
        "/selicplus - investimentos que superam a Selic\n\n"
        "🚨 Alertas automáticos\n"
        "/setalertchat - define este chat para receber alertas\n"
        "/alertastatus - mostra o estado dos alertas automáticos\n"
        "/testealerta - envia um alerta de teste\n\n"
        "💡 Dica\n"
        "Use /menu quando quiser ver a lista completa de comandos."
    )


def build_about_text():
    return (
        f"ℹ️ Sobre o {BOT_NAME}\n\n"
        "O Radar de Investimentos monitora oportunidades de renda fixa no Brasil.\n\n"
        "O sistema analisa automaticamente CDBs, LCIs e LCAs de múltiplas fontes públicas "
        "e organiza as melhores oportunidades em um ranking.\n\n"
        "Principais recursos:\n"
        "• ranking automático de oportunidades\n"
        "• score mais inteligente\n"
        "• detecção de investimentos que superam a Selic\n"
        "• filtros por liquidez diária e prazo\n"
        "• identificação de oportunidades raras reais\n"
        "• melhor taxa do radar no momento\n"
        "• alertas automáticos\n"
        "• detecção de novas oportunidades\n"
        "• detecção de melhoria de taxa\n"
        "• histórico do radar\n\n"
        "Use /menu para acessar todos os comandos do radar."
    )


def build_sources_text():
    build_ranked_data()
    source_status = get_source_status()

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

    msg = "📡 Fontes monitoradas pelo radar\n\n"

    if active_sources:
        msg += "✅ Fontes ativas\n"
        msg += "\n".join(active_sources)
        msg += "\n\n"

    if inactive_sources:
        msg += "⚠️ Fontes sem retorno no momento\n"
        msg += "\n".join(inactive_sources)
        msg += "\n\n"

    if fallback_line:
        msg += fallback_line

    return msg.strip()


def build_stats_text():
    ranked = build_ranked_data()
    source_status = get_source_status()

    total = len(ranked)
    reais = sum(1 for i in ranked if i.get("bank") != "Simulação Interna")
    beats_selic = sum(1 for i in ranked if i.get("net", 0) > SELIC)
    diarios = sum(1 for i in ranked if i.get("type_normalized") == "CDB" and i.get("liquidity"))
    curtos = sum(1 for i in ranked if i.get("type_normalized") == "CDB" and i.get("days", 0) <= 365)
    isentos = sum(1 for i in ranked if i.get("type_normalized") in ["LCI", "LCA"])
    raras = sum(1 for i in ranked if i.get("rare"))

    if ranked:
        best_rate = max(i["rate"] for i in ranked)
        bests = sum(1 for i in ranked if i["rate"] == best_rate)
    else:
        bests = 0

    fontes_ativas = sum(
        1 for source_name, info in source_status.items()
        if source_name != "fallback" and info.get("count", 0) > 0
    )

    return (
        "📊 Estatísticas do Radar\n\n"
        f"Oportunidades analisadas: {total}\n"
        f"Oportunidades reais: {reais}\n"
        f"Fontes ativas: {fontes_ativas}\n\n"
        f"Melhores que Selic: {beats_selic}\n"
        f"Liquidez diária: {diarios}\n"
        f"Curto prazo: {curtos}\n"
        f"LCI/LCA (isentos): {isentos}\n"
        f"Oportunidades raras reais: {raras}\n"
        f"Melhores taxas marcadas: {bests}"
    )


# =========================================================
# COMMANDS
# =========================================================

async def start_cmd(update, context):
    register_current_chat(update)
    await update.message.reply_text(
        build_main_menu_text(),
        reply_markup=ReplyKeyboardRemove()
    )


async def menu_cmd(update, context):
    register_current_chat(update)
    await update.message.reply_text(
        build_main_menu_text(),
        reply_markup=ReplyKeyboardRemove()
    )


async def help_cmd(update, context):
    register_current_chat(update)
    await update.message.reply_text(
        build_help_text(),
        reply_markup=ReplyKeyboardRemove()
    )


async def about_cmd(update, context):
    register_current_chat(update)
    await update.message.reply_text(
        build_about_text(),
        reply_markup=ReplyKeyboardRemove()
    )


async def fontes_cmd(update, context):
    register_current_chat(update)
    await update.message.reply_text(
        build_sources_text(),
        reply_markup=ReplyKeyboardRemove()
    )


async def stats_cmd(update, context):
    register_current_chat(update)
    await update.message.reply_text(
        build_stats_text(),
        reply_markup=ReplyKeyboardRemove()
    )


async def novas_cmd(update, context):
    register_current_chat(update)

    ranked = build_ranked_data()
    new_items, _changed_items = scan_market_changes(ranked)

    if not new_items:
        await update.message.reply_text(
            "🆕 Nenhuma nova oportunidade detectada no momento.\n\n"
            "O radar já analisou todas as oportunidades disponíveis nas fontes.",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    msg = "🆕 Novas oportunidades detectadas\n\n"

    for i, r in enumerate(new_items[:10], 1):
        msg += format_item(i, r)

    await update.message.reply_text(
        msg,
        reply_markup=ReplyKeyboardRemove()
    )


async def mudancas_cmd(update, context):
    register_current_chat(update)

    ranked = build_ranked_data()
    _new_items, changed_items = scan_market_changes(ranked)

    if not changed_items:
        await update.message.reply_text(
            "📉 Nenhuma mudança de taxa detectada no momento.\n\n"
            "As oportunidades monitoradas permanecem com as mesmas condições.",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    melhorias = [c for c in changed_items if c["new"].get("rate", 0) > c["old"].get("rate", 0)]
    quedas = [c for c in changed_items if c["new"].get("rate", 0) < c["old"].get("rate", 0)]

    msg = "📈 Mudanças de taxa detectadas\n\n"

    if melhorias:
        msg += "✅ Melhorias de taxa\n\n"
        for i, change in enumerate(melhorias[:10], 1):
            msg += format_change_item(i, change)

    if quedas:
        msg += "⚠️ Quedas de taxa\n\n"
        for i, change in enumerate(quedas[:10], 1):
            msg += format_change_item(i, change)

    await update.message.reply_text(
        msg,
        reply_markup=ReplyKeyboardRemove()
    )


async def historico_cmd(update, context):
    register_current_chat(update)

    state = load_market_state()
    events = state.get("events", [])

    if not events:
        await update.message.reply_text(
            "🕘 Histórico vazio no momento.",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    last_events = events[-10:]
    last_events.reverse()

    msg = "🕘 Histórico do Radar\n\n"

    for i, event in enumerate(last_events, 1):
        kind = event.get("kind")
        timestamp = event.get("timestamp", "N/A")
        item = event.get("item", {})

        if kind == "new":
            msg += (
                f"{i}️⃣ 🆕 Nova oportunidade\n"
                f"🕒 {timestamp}\n"
                f"💼 {item.get('type')} {item.get('rate')}% CDI\n"
                f"🏦 {item.get('bank')}\n\n"
            )
        elif kind == "rate_change":
            direction = "📈 Melhoria de taxa" if event.get("new_rate", 0) > event.get("old_rate", 0) else "📉 Queda de taxa"
            msg += (
                f"{i}️⃣ {direction}\n"
                f"🕒 {timestamp}\n"
                f"💼 {item.get('type')}\n"
                f"🏦 {item.get('bank')}\n"
                f"🔁 Antes: {event.get('old_rate')}% CDI\n"
                f"✨ Agora: {event.get('new_rate')}% CDI\n\n"
            )

    await update.message.reply_text(
        msg,
        reply_markup=ReplyKeyboardRemove()
    )


async def raras_cmd(update, context):
    register_current_chat(update)
    await update.message.reply_text(
        build_real_rare_text(),
        reply_markup=ReplyKeyboardRemove()
    )


async def melhortaxa_cmd(update, context):
    register_current_chat(update)
    await update.message.reply_text(
        build_best_rate_text(),
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
    diarios = sum(1 for i in ranked if i.get("type_normalized") == "CDB" and i.get("liquidity"))
    curtos = sum(1 for i in ranked if i.get("type_normalized") == "CDB" and i.get("days", 0) <= 365)
    isentos = sum(1 for i in ranked if i.get("type_normalized") in ["LCI", "LCA"])

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
    diarios = [r for r in ranked if r.get("type_normalized") == "CDB" and r.get("liquidity")]

    if not diarios:
        await update.message.reply_text(
            "💧 Nenhuma oportunidade com liquidez diária encontrada nas fontes ativas no momento."
        )
        return

    msg = "💧 CDBs de liquidez diária\n\n"

    for i, r in enumerate(diarios[:10], 1):
        msg += format_item(i, r)

    await update.message.reply_text(msg)


async def curtos_cmd(update, context):
    register_current_chat(update)

    ranked = build_ranked_data()
    curtos = [r for r in ranked if r.get("type_normalized") == "CDB" and r.get("days", 0) <= 365]

    if not curtos:
        await update.message.reply_text(
            "⏱ Nenhuma oportunidade de curto prazo encontrada nas fontes ativas no momento."
        )
        return

    msg = "⏱ CDBs de curto prazo\n\n"

    for i, r in enumerate(curtos[:10], 1):
        msg += format_item(i, r)

    await update.message.reply_text(msg)


async def isentos_cmd(update, context):
    register_current_chat(update)

    ranked = build_ranked_data()
    isentos = [r for r in ranked if r.get("type_normalized") in ["LCI", "LCA"]]

    if not isentos:
        await update.message.reply_text(
            "🟢 Nenhum investimento isento encontrado nas fontes ativas no momento."
        )
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
        await update.message.reply_text(
            "🚀 Nenhum investimento supera a Selic nas fontes ativas no momento."
        )
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
        "type_normalized": "CDB",
        "rate": 125,
        "bank": "Banco Teste",
        "days": 365,
        "liquidity": True,
        "gross": 13.31,
        "net": 11.34,
        "score": 12,
        "classification": "🔴 OPORTUNIDADE IMPERDÍVEL",
        "rare": True,
        "best_rate": True,
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
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("about", about_cmd))
    app.add_handler(CommandHandler("fontes", fontes_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("novas", novas_cmd))
    app.add_handler(CommandHandler("mudancas", mudancas_cmd))
    app.add_handler(CommandHandler("historico", historico_cmd))
    app.add_handler(CommandHandler("raras", raras_cmd))
    app.add_handler(CommandHandler("melhortaxa", melhortaxa_cmd))
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
