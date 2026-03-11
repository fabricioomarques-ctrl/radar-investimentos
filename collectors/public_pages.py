import requests
from bs4 import BeautifulSoup

PAGES = []


def collect():
    results = []

    for url in PAGES:
        try:
            r = requests.get(url, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")

            text = soup.get_text()

            if "cdb" in text.lower():
                results.append({
                    "bank": "Fonte Pública",
                    "type": "CDB",
                    "rate": 105,
                    "days": 365,
                    "liquidity": False
                })

        except Exception:
            pass

    return results
