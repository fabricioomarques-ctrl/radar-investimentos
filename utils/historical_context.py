import json
import os
from datetime import datetime


HISTORICAL_CONTEXT_FILE = "historical_context.json"


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


def _normalize_bank(bank):
    return str(bank or "").strip().lower() or "mercado"


def _normalize_type(inv_type):
    text = str(inv_type or "").strip().lower()

    if "lci" in text:
        return "LCI"
    if "lca" in text:
        return "LCA"
    if "cdb" in text:
        return "CDB"

    return str(inv_type or "").strip().upper() or "INVESTIMENTO"


def _avg(values):
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def load_historical_context():
    return load_json_file(
        HISTORICAL_CONTEXT_FILE,
        {
            "last_update": None,
            "by_bank": {},
            "by_type": {},
            "recent_best_by_type": {}
        }
    )


def update_historical_context(items, window_size=60):
    """
    Guarda histórico simples de taxas observadas:
    - por banco
    - por categoria
    - melhor taxa recente por categoria
    """
    ctx = load_historical_context()

    by_bank = ctx.get("by_bank", {})
    by_type = ctx.get("by_type", {})
    recent_best_by_type = ctx.get("recent_best_by_type", {})

    grouped_best = {}

    for item in items:
        bank = _normalize_bank(item.get("bank"))
        inv_type = _normalize_type(item.get("type"))
        rate = float(item.get("rate", 0))

        if rate <= 0:
            continue

        if bank not in by_bank:
            by_bank[bank] = []

        by_bank[bank].append(rate)
        by_bank[bank] = by_bank[bank][-window_size:]

        if inv_type not in by_type:
            by_type[inv_type] = []

        by_type[inv_type].append(rate)
        by_type[inv_type] = by_type[inv_type][-window_size:]

        if inv_type not in grouped_best or rate > grouped_best[inv_type]:
            grouped_best[inv_type] = rate

    for inv_type, best_rate in grouped_best.items():
        if inv_type not in recent_best_by_type:
            recent_best_by_type[inv_type] = []

        recent_best_by_type[inv_type].append(best_rate)
        recent_best_by_type[inv_type] = recent_best_by_type[inv_type][-window_size:]

    ctx["by_bank"] = by_bank
    ctx["by_type"] = by_type
    ctx["recent_best_by_type"] = recent_best_by_type
    ctx["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    save_json_file(HISTORICAL_CONTEXT_FILE, ctx)
    return ctx


def enrich_with_historical_context(items):
    """
    Enriquecimento não destrutivo:
    - bank_avg_history
    - type_avg_history
    - recent_best_history
    - above_bank_history
    - above_type_history
    - best_recent_level
    """
    ctx = load_historical_context()

    by_bank = ctx.get("by_bank", {})
    by_type = ctx.get("by_type", {})
    recent_best_by_type = ctx.get("recent_best_by_type", {})

    enriched = []

    for item in items:
        bank = _normalize_bank(item.get("bank"))
        inv_type = _normalize_type(item.get("type"))
        rate = float(item.get("rate", 0))

        bank_history = by_bank.get(bank, [])
        type_history = by_type.get(inv_type, [])
        recent_best_history = recent_best_by_type.get(inv_type, [])

        bank_avg = _avg(bank_history)
        type_avg = _avg(type_history)
        recent_best_avg = _avg(recent_best_history)

        row = dict(item)
        row["bank_avg_history"] = bank_avg
        row["type_avg_history"] = type_avg
        row["recent_best_history"] = recent_best_avg

        row["above_bank_history"] = bank_avg > 0 and rate >= bank_avg + 1.0
        row["above_type_history"] = type_avg > 0 and rate >= type_avg + 1.0
        row["best_recent_level"] = recent_best_avg > 0 and rate >= recent_best_avg

        enriched.append(row)

    return enriched
