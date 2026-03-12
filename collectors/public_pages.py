import requests
from bs4 import BeautifulSoup

SOURCES = [
    "https://www.infomoney.com.br/guias/cdb/",
    "https://www.infomoney.com.br/guias/lci-lca/",
]


def collect():

    results = []

    for url in SOURCES:

        try:
            r = requests.get(url, timeout=20)

            if r.status_code != 200:
                continue

            soup = BeautifulSoup(r.text, "html.parser")

            tables = soup.find_all("table")

            for table in tables:

                rows = table.find_all("tr")

                for row in rows:

                    cols = [c.text.strip() for c in row.find_all("td")]

                    if len(cols) < 2:
                        continue

                    name = cols[0]

                    if "%" not in row.text:
                        continue

                    results.append({
                        "bank": "Mercado",
                        "type": name,
                        "rate": 110,
                        "days": 365,
                        "liquidity": False,
                        "source": "PublicPages",
                        "url": url
                    })

        except Exception:
            continue

    return results
