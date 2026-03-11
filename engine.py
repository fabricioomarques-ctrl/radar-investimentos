from collectors.yubb import collect as yubb_collect
from collectors.public_pages import collect as pages_collect
from collectors.fallback import get_fallback


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
    data = []

    y = yubb_collect()
    data.extend(y)

    p = pages_collect()
    data.extend(p)

    data = deduplicate(data)

    if not data:
        data.extend(get_fallback())

    return data
