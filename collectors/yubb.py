from playwright.sync_api import sync_playwright

from utils.parser import (
    extract_cdi,
    extract_bank,
    extract_product_type,
    extract_term_days,
    extract_liquidity,
)

URL = "https://yubb.com.br/investimentos/renda-fixa"


def collect():
    results = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            page.goto(URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(5000)

            # tenta descer a página para carregar cards lazy
            for _ in range(4):
                page.mouse.wheel(0, 3000)
                page.wait_for_timeout(1500)

            content = page.content()
            text = page.locator("body").inner_text()

            browser.close()

        candidate_texts = []

        # blocos maiores primeiro
        chunks = text.split("\n")
        for chunk in chunks:
            c = chunk.strip()
            if c and "%" in c and any(x in c.lower() for x in ["cdb", "lci", "lca"]):
                candidate_texts.append(c)

        # janelas de texto para capturar contexto
        words = text.split()
        for i in range(0, len(words), 25):
            window = " ".join(words[i:i+60])
            if "%" in window and any(x in window.lower() for x in ["cdb", "lci", "lca"]):
                candidate_texts.append(window)

        seen = set()

        for raw in candidate_texts:
            product_type = extract_product_type(raw)
            rate = extract_cdi(raw)

            if not product_type or rate is None:
                continue

            bank = extract_bank(raw) or "Banco não identificado"
            days = extract_term_days(raw)
            liquidity = extract_liquidity(raw)

            key = (bank, product_type, rate, days, liquidity)
            if key in seen:
                continue
            seen.add(key)

            results.append({
                "bank": bank,
                "type": product_type,
                "rate": rate,
                "days": days,
                "liquidity": liquidity,
                "source": "Yubb",
                "url": URL,
            })

    except Exception:
        return []

    return results
