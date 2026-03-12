import requests
from bs4 import BeautifulSoup


URL = "https://investidor10.com.br/renda-fixa/"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def collect():

    results = []

    try:

        r = requests.get(URL, headers=HEADERS, timeout=20)

        if r.status_code != 200:
            return []

        soup = BeautifulSoup(r.text, "html.parser")

        text = soup.get_text(" ", strip=True)

        words = text.split()

        for w in words:

            if "%" in w:

                try:

                    rate = float(w.replace("%", "").replace(",", "."))

                except:
                    continue

                if rate < 80:
                    continue

                results.append({

                    "bank": "Mercado",
                    "type": "CDB",
                    "rate": rate,
                    "days": 365,
                    "liquidity": False,
                    "source": "Investidor10",
                    "url": URL

                })

    except Exception:

        return []

    return results
