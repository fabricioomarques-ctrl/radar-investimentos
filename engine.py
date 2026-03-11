from collectors.yubb import collect as yubb_collect
from collectors.public_pages import collect as pages_collect
from collectors.fallback import get_fallback


def collect_all():
    data = []

    y = yubb_collect()
    data.extend(y)

    p = pages_collect()
    data.extend(p)

    if not data:
        data.extend(get_fallback())

    return data
