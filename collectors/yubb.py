import re
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from utils.parser import (
    extract_cdi,
    extract_bank,
    extract_product_type,
    extract_term_days,
    extract_liquidity,
)

URL = "https://yubb.com.br/investimentos/renda-fixa"


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _looks_like_product_block(text: str) -> bool:
    low = text.lower()
    has_product = any(x in low for x in ["cdb", "lci", "lca"])
    has_percent = "%" in text
    return has_product and has_percent and len(text) >= 20


def _extract_candidate_blocks_from_html(html: str):
    soup = BeautifulSoup(html, "html.parser")
    candidates = []

    # 1) blocos visuais principais
    for tag in soup.find_all(["article", "section", "div", "li", "tr"]):
        txt = _clean_text(tag.get_text(" ", strip=True))
        if _looks_like_product_block(txt):
            candidates.append(txt)

    # 2) scripts embutidos
    for script in soup.find_all("script"):
        txt = _clean_text(script.get_text(" ", strip=True))
        if not txt:
            continue

        # quebra em pedaços menores para facilitar leitura
        parts = re.split(r"[{}\[\];\n]+", txt)
        for part in parts:
            p = _clean_text(part)
            if _looks_like_product_block(p):
                candidates.append(p)

    # 3) fallback no texto geral da página
    full_text = _clean_text(soup.get_text(" ", strip=True))
    windows = re.findall(
        r"(.{0,160}(?:cdb|lci|lca).{0,260})",
        full_text,
        flags=re.IGNORECASE,
    )
    for w in windows:
        w = _clean_text(w)
        if _looks_like_product_block(w):
            candidates.append(w)

    # remove duplicados preservando ordem
    unique = []
    seen = set()
    for c in candidates:
        key = c.lower()
        if key not in seen:
            seen.add(key)
            unique.append(c)

    return unique


def collect():
    results = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
            )

            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1440, "height": 2400},
                locale="pt-BR",
            )

            page = context.new_page()

            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector("body", timeout=60000)
            page.wait_for_timeout(8000)

            # tenta rolar a página inteira para disparar carregamento lazy
            for _ in range(10):
                page.mouse.wheel(0, 5000)
                page.wait_for_timeout(1500)

            # volta um pouco para cima também
            for _ in range(2):
                page.mouse.wheel(0, -3000)
                page.wait_for_timeout(1000)

            html = page.content()

            context.close()
            browser.close()

        candidate_texts = _extract_candidate_blocks_from_html(html)

        seen_products = set()

        for raw in candidate_texts:
            product_type = extract_product_type(raw)
            rate = extract_cdi(raw)

            if not product_type or rate is None:
                continue

            bank = extract_bank(raw) or "Banco não identificado"
            days = extract_term_days(raw)
            liquidity = extract_liquidity(raw)

            key = (
                bank.strip().lower(),
                product_type.strip().lower(),
                float(rate),
                int(days),
                bool(liquidity),
            )

            if key in seen_products:
                continue
            seen_products.add(key)

            results.append({
                "bank": bank,
                "type": product_type,
                "rate": rate,
                "days": days,
                "liquidity": liquidity,
                "source": "Yubb",
                "url": URL,
            })

        return results

    except Exception as e:
        print(f"[YUBB ERROR] {e}")
        return []
