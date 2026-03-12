from collectors.yubb import collect as collect_yubb
from collectors.public_pages import collect as collect_public
from collectors.fallback import get_fallback

try:
    from collectors.maisretorno import collect as collect_maisretorno
except Exception:
    collect_maisretorno = None

try:
    from collectors.investidor10 import collect as collect_investidor10
except Exception:
    collect_investidor10 = None

try:
    from collectors.statusinvest import collect as collect_statusinvest
except Exception:
    collect_statusinvest = None


LAST_SOURCE_STATUS = {
    "yubb": {"ok": False, "count": 0, "error": ""},
    "public_pages": {"ok": False, "count": 0, "error": ""},
    "maisretorno": {"ok": False, "count": 0, "error": "não configurado"},
    "investidor10": {"ok": False, "count": 0, "error": "não configurado"},
    "statusinvest": {"ok": False, "count": 0, "error": "não configurado"},
    "fallback": {"ok": False, "count": 0, "error": ""},
}


def normalize_bank(bank):
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


def normalize_type(inv_type):
    inv_type = str(inv_type or "").strip().upper()

    aliases = {
        "LCI/LCA": "LCI_LCA",
        "LCA/LCI": "LCI_LCA",
    }

    return aliases.get(inv_type, inv_type)


def normalize_days(days):
    try:
        return int(float(days))
    except Exception:
        return 365


def normalize_rate(rate):
    try:
        return round(float(rate), 2)
    except Exception:
        return 0.0


def normalize_liquidity(liquidity):
    return bool(liquidity)


def build_dedup_key(item):
    return (
        normalize_bank(item.get("bank")),
        normalize_type(item.get("type")),
        normalize_rate(item.get("rate")),
        normalize_days(item.get("days")),
        normalize_liquidity(item.get("liquidity")),
    )


def deduplicate(data):
    seen = set()
    unique = []

    for item in data:
        key = build_dedup_key(item)

        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique


def _collect_from_source(source_name, collector_fn, data):
    global LAST_SOURCE_STATUS

    if collector_fn is None:
        LAST_SOURCE_STATUS[source_name]["ok"] = False
        LAST_SOURCE_STATUS[source_name]["count"] = 0
        LAST_SOURCE_STATUS[source_name]["error"] = "não configurado"
        return

    try:
        items = collector_fn()

        if not isinstance(items, list):
            LAST_SOURCE_STATUS[source_name]["ok"] = False
            LAST_SOURCE_STATUS[source_name]["count"] = 0
            LAST_SOURCE_STATUS[source_name]["error"] = "coletor retornou formato inválido"
            return

        data.extend(items)

        LAST_SOURCE_STATUS[source_name]["ok"] = True
        LAST_SOURCE_STATUS[source_name]["count"] = len(items)

        if len(items) == 0:
            LAST_SOURCE_STATUS[source_name]["error"] = "nenhum produto encontrado"

    except Exception as e:
        LAST_SOURCE_STATUS[source_name]["ok"] = False
        LAST_SOURCE_STATUS[source_name]["count"] = 0
        LAST_SOURCE_STATUS[source_name]["error"] = str(e)


def collect_all():
    global LAST_SOURCE_STATUS

    LAST_SOURCE_STATUS = {
        "yubb": {"ok": False, "count": 0, "error": ""},
        "public_pages": {"ok": False, "count": 0, "error": ""},
        "maisretorno": {"ok": False, "count": 0, "error": ""},
        "investidor10": {"ok": False, "count": 0, "error": ""},
        "statusinvest": {"ok": False, "count": 0, "error": ""},
        "fallback": {"ok": False, "count": 0, "error": ""},
    }

    data = []

    _collect_from_source("yubb", collect_yubb, data)
    _collect_from_source("public_pages", collect_public, data)
    _collect_from_source("maisretorno", collect_maisretorno, data)
    _collect_from_source("investidor10", collect_investidor10, data)
    _collect_from_source("statusinvest", collect_statusinvest, data)

    data = deduplicate(data)

    if not data:
        try:
            f = get_fallback()
            data.extend(f)
            LAST_SOURCE_STATUS["fallback"]["ok"] = True
            LAST_SOURCE_STATUS["fallback"]["count"] = len(f)

            if len(f) == 0:
                LAST_SOURCE_STATUS["fallback"]["error"] = "fallback vazio"

        except Exception as e:
            LAST_SOURCE_STATUS["fallback"]["ok"] = False
            LAST_SOURCE_STATUS["fallback"]["count"] = 0
            LAST_SOURCE_STATUS["fallback"]["error"] = str(e)

    return data


def get_source_status():
    return LAST_SOURCE_STATUS
