import requests
from bs4 import BeautifulSoup
from utils.parser import extract_cdi

URL = "https://yubb.com.br/investimentos/renda-fixa"


def collect():
    data = []

    try:
        r = requests.get(URL, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        blocks = soup.find_all("div")

        for b in blocks:
            text = b.get_text(" ", strip=True)

            if "cdb" in text.lower():
                rate = extract_cdi(text)
                if rate:
                    data.append({
                        "bank": "Banco não identificado",
                        "type": "CDB",
                        "rate": rate,
                        "days": 365,
                        "liquidity": False
                    })

    except Exception:
        pass

    return data
