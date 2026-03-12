from collectors.yubb import collect as collect_yubb
from collectors.public_pages import collect as collect_public
from collectors.fallback import get_fallback

# Fontes opcionais futuras:
# se o arquivo não existir, o sistema continua normal
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


def deduplicate(data):
    seen = set()
    unique = []

    for item in data:
        key = (
            item.get("bank"),
            item.get("type"),
            item.get("rate"),
            item.get("days"),
            item.get("liquidity"),
        )

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
