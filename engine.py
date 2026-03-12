from collectors.yubb import collect as collect_yubb
from collectors.investidor10 import collect as collect_investidor10
from collectors.maisretorno import collect as collect_maisretorno
from collectors.fallback import get_fallback


LAST_SOURCE_STATUS = {}


def deduplicate(data):

    seen = set()
    unique = []

    for item in data:

        key = (
            item.get("bank"),
            item.get("type"),
            item.get("rate"),
            item.get("days"),
            item.get("liquidity")
        )

        if key not in seen:

            seen.add(key)
            unique.append(item)

    return unique


def _validate_items(items):

    valid = []

    for i in items:

        if not isinstance(i, dict):
            continue

        if not i.get("rate"):
            continue

        if i.get("rate") <= 0:
            continue

        if not i.get("type"):
            continue

        if not i.get("days"):
            i["days"] = 365

        if not i.get("bank"):
            i["bank"] = "Mercado"

        valid.append(i)

    return valid


def collect_all():

    global LAST_SOURCE_STATUS

    LAST_SOURCE_STATUS = {
        "yubb": {"ok": False, "count": 0, "error": ""},
        "investidor10": {"ok": False, "count": 0, "error": ""},
        "maisretorno": {"ok": False, "count": 0, "error": ""},
        "fallback": {"ok": False, "count": 0, "error": ""}
    }

    data = []

    collectors = {
        "yubb": collect_yubb,
        "investidor10": collect_investidor10,
        "maisretorno": collect_maisretorno
    }

    for name, func in collectors.items():

        try:

            items = func()

            items = _validate_items(items)

            data.extend(items)

            LAST_SOURCE_STATUS[name]["ok"] = True
            LAST_SOURCE_STATUS[name]["count"] = len(items)

            if len(items) == 0:
                LAST_SOURCE_STATUS[name]["error"] = "nenhum produto encontrado"

        except Exception as e:

            LAST_SOURCE_STATUS[name]["error"] = str(e)

    data = deduplicate(data)

    if not data:

        f = get_fallback()

        data.extend(f)

        LAST_SOURCE_STATUS["fallback"]["ok"] = True
        LAST_SOURCE_STATUS["fallback"]["count"] = len(f)

    return data


def get_source_status():

    return LAST_SOURCE_STATUS
