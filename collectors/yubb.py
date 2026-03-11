import requests
from bs4 import BeautifulSoup

from utils.parser import (
    extract_cdi,
    extract_bank,
    extract_product_type,
    extract_term_days,
    extract_liquidity,
)


URLS = [
    "https://yubb.com.br/investimentos/renda-fixa",
    "https://yubb.com.br",
]


def collect():
    results = []

    for url in URLS:
        try:
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            soup = BeautifulSoup(r.text, "html.parser")

            # Junta blocos visuais e scripts para tentar capturar mais texto
            candidate_texts = []

            for tag in soup.find_all(["div", "article", "section", "li", "span", "p"]):
                text = tag.get_text(" ", strip=True)
                if text and "%" in text:
                    candidate_texts.append(text)

            for script in soup.find_all("script"):
                text = script.get_text(" ", strip=True)
                if text and "%" in text:
                    candidate_texts.append(text)

            for text in candidate_texts:
                product_type = extract_product_type(text)
                rate = extract_cdi(text)

                if not product_type or rate is None:
                    continue

                bank = extract_bank(text)
                days = extract_term_days(text)
                liquidity = extract_liquidity(text)

                results.append({
                    "bank": bank or "Banco não identificado",
                    "type": product_type,
                    "rate": rate,
                    "days": days,
                    "liquidity": liquidity,
                    "source": "Yubb",
                    "url": url,
                })

            if results:
                break

        except Exception:
            pass

    return results
