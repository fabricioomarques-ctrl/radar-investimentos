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

            bank = item.get("bank")

            if not bank:
                bank = item.get("issuer", "Mercado")

            inv_type = item.get("type", "CDB")

            rate = item.get("rate")

            if not rate:
                continue

            term = item.get("term", 365)

            liquidity = item.get("liquidity", False)

            results.append({

                "bank": bank,

                "type": inv_type,

                "rate": float(rate),

                "days": int(term),

                "liquidity": bool(liquidity),

                "source": "Yubb",

                "url": "https://yubb.com.br/investimentos/renda-fixa"

            })

    except Exception:

        return []

    return results
