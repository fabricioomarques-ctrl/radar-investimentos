from collectors.yubb import collect as yubb_collect
from collectors.public_pages import collect as pages_collect
from collectors.fallback import get_fallback


LAST_SOURCE_STATUS = {
    "yubb": {"ok": False, "count": 0, "error": ""},
    "public_pages": {"ok": False, "count": 0, "error": ""},
    "fallback": {"ok": False, "count": 0, "error": ""},
}


def deduplicate(data):
    unique = []
    seen = set()

    for item in data:
        key = (
            str(item.get("bank", "")).strip().lower(),
            str(item.get("type", "")).strip().lower(),
            float(item.get("rate", 0)),
            int(item.get("days", 0)),
            bool(item.get("liquidity", False)),
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

    try:
        y = yubb_collect()
        data.extend(y)
        LAST_SOURCE_STATUS["yubb"]["ok"] = True
        LAST_SOURCE_STATUS["yubb"]["count"] = len(y)
        if len(y) == 0:
            LAST_SOURCE_STATUS["yubb"]["error"] = "coletor executou, mas não encontrou produtos válidos"
    except Exception as e:
        LAST_SOURCE_STATUS["yubb"]["error"] = str(e)

    try:
        p = pages_collect()
        data.extend(p)
        LAST_SOURCE_STATUS["public_pages"]["ok"] = True
        LAST_SOURCE_STATUS["public_pages"]["count"] = len(p)
        if len(p) == 0:
            LAST_SOURCE_STATUS["public_pages"]["error"] = "nenhuma página pública retornou produtos válidos"
    except Exception as e:
        LAST_SOURCE_STATUS["public_pages"]["error"] = str(e)

    data = deduplicate(data)

    if not data:
        f = get_fallback()
        data.extend(f)
        LAST_SOURCE_STATUS["fallback"]["ok"] = True
        LAST_SOURCE_STATUS["fallback"]["count"] = len(f)

    return data


def get_source_status():
    return LAST_SOURCE_STATUS
