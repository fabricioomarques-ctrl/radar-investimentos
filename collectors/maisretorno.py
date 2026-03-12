import requests
from bs4 import BeautifulSoup
from utils.bank_detector import detect_bank


URL = "https://maisretorno.com/renda-fixa"


def collect():

    results = []

    try:

        r = requests.get(URL, timeout=20)

        if r.status_code != 200:
            return []

        soup = BeautifulSoup(r.text, "html.parser")

        cards = soup.find_all("div")

        for card in cards:

            text = card.get_text(" ", strip=True)

            if "%" not in text:
                continue

            rate = None

            for part in text.split():

                if "%" in part:

                    try:
                        rate = float(part.replace("%", "").replace(",", "."))
                    except:
                        pass

            if rate is None:
                continue

            bank = detect_bank(text)

            results.append({
                "bank": bank,
                "type": "CDB",
                "rate": rate,
                "days": 365,
                "liquidity": False,
                "source": "MaisRetorno",
                "url": URL
            })

    except:
        return []

    return results
