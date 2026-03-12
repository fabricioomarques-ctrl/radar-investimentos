import requests
from bs4 import BeautifulSoup
from utils.bank_detector import detect_bank


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

        cards = soup.find_all("tr")

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
                "source": "Investidor10",
                "url": URL
            })

    except:
        return []

    return results
