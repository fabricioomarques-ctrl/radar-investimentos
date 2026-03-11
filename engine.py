from collectors.yubb import collect as collect_yubb
from collectors.public_pages import collect as collect_public
from collectors.fallback import get_fallback

LAST_SOURCE_STATUS = {
    "yubb": {"ok": False, "count": 0, "error": ""},
    "public_pages": {"ok": False, "count": 0, "error": ""},
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


def collect_all():
    global LAST_SOURCE_STATUS

    LAST_SOURCE_STATUS = {
        "yubb": {"ok": False, "count": 0, "error": ""},
        "public_pages": {"ok": False, "count": 0, "error": ""},
        "fallback": {"ok": False, "count": 0, "error": ""},
    }

    data = []

    # YUBB
    try:
        y = collect_yubb()
        data.extend(y)
        LAST_SOURCE_STATUS["yubb"]["ok"] = True
        LAST_SOURCE_STATUS["yubb"]["count"] = len(y)

        if len(y) == 0:
            LAST_SOURCE_STATUS["yubb"]["error"] = "não encontrou produtos válidos"

    except Exception as e:
        LAST_SOURCE_STATUS["yubb"]["error"] = str(e)

    # PÁGINAS PÚBLICAS
    try:
        p = collect_public()
        data.extend(p)
        LAST_SOURCE_STATUS["public_pages"]["ok"] = True
        LAST_SOURCE_STATUS["public_pages"]["count"] = len(p)

        if len(p) == 0:
            LAST_SOURCE_STATUS["public_pages"]["error"] = "nenhum produto encontrado"

    except Exception as e:
        LAST_SOURCE_STATUS["public_pages"]["error"] = str(e)

    data = deduplicate(data)

    # FALLBACK
    if not data:
        f = get_fallback()
        data.extend(f)
        LAST_SOURCE_STATUS["fallback"]["ok"] = True
        LAST_SOURCE_STATUS["fallback"]["count"] = len(f)

    return data


def get_source_status():
    return LAST_SOURCE_STATUS
