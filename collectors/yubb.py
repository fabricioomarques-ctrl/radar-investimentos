import requests

API_URLS = [
    "https://api.yubb.com.br/investments/fixed-income",
    "https://api.yubb.com.br/investments/fixed-income/",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/145.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://yubb.com.br/investimentos/renda-fixa",
}


def _safe_float(value, default=100.0):
    try:
        return float(str(value).replace("%", "").replace(",", ".").strip())
    except Exception:
        return default


def _safe_int(value, default=365):
    try:
        return int(float(str(value).replace(",", ".").strip()))
    except Exception:
        return default


def _safe_bool(value):
    if isinstance(value, bool):
        return value

    text = str(value).strip().lower()
    return text in {"1", "true", "sim", "yes", "y"}


def _normalize_item(item):
    return {
        "bank": item.get("bank") or item.get("bank_name") or item.get("institution") or "Banco",
        "type": item.get("type") or item.get("product_type") or "CDB",
        "rate": _safe_float(item.get("rate", 100)),
        "days": _safe_int(item.get("term", item.get("days", 365))),
        "liquidity": _safe_bool(item.get("liquidity", False)),
        "source": "Yubb",
        "url": "https://yubb.com.br/investimentos/renda-fixa",
    }


def collect():
    results = []

    for api_url in API_URLS:
        try:
            r = requests.get(api_url, headers=HEADERS, timeout=20)

            if r.status_code != 200:
                continue

            data = r.json()

            if not isinstance(data, list):
                continue

            for item in data:
                try:
                    normalized = _normalize_item(item)
                    results.append(normalized)
                except Exception:
                    continue

            if results:
                return results

        except Exception:
            continue

    return []
