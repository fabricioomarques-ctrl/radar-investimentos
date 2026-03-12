import requests
from bs4 import BeautifulSoup


URL = "https://yubb.com.br/investimentos/renda-fixa"


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

        for i, w in enumerate(words):

            if "%CDI" in w.upper() or "% CDI" in w.upper():

                try:

                    rate = float(
                        w.replace("%", "")
                        .replace("CDI", "")
                        .replace(",", ".")
                    )

                except:
                    continue

                results.append({

                    "bank": "Mercado",
                    "type": "CDB",
                    "rate": rate,
                    "days": 365,
                    "liquidity": False,
                    "source": "Yubb",
                    "url": URL

                })

    except Exception:

        return []

    return results
