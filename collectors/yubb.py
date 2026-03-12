import requests

API_URL = "https://api.yubb.com.br/investments/fixed-income"


def collect():

    results = []

    try:

        r = requests.get(API_URL, timeout=20)

        if r.status_code != 200:
            return []

        data = r.json()

        for item in data:

            results.append({
                "bank": item.get("bank", "Banco"),
                "type": item.get("type", "CDB"),
                "rate": float(item.get("rate", 100)),
                "days": int(item.get("term", 365)),
                "liquidity": bool(item.get("liquidity", False)),
                "source": "Yubb",
                "url": "https://yubb.com.br/investimentos/renda-fixa"
            })

    except Exception:
        return []

    return results
