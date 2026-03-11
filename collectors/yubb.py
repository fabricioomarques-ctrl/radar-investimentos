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


def _extract_candidate_blocks_from_html(html: str):
    soup = BeautifulSoup(html, "html.parser")
    candidates = []

    # 1) Blocos visuais comuns
    for tag in soup.find_all(["article", "section", "div", "li"]):
        txt = _clean_text(tag.get_text(" ", strip=True))
        low = txt.lower()

        if not txt or len(txt) < 20:
            continue

        if any(x in low for x in ["cdb", "lci", "lca"]) and "%" in txt:
            candidates.append(txt)

    # 2) Scripts embutidos com dados renderizados
    for script in soup.find_all("script"):
        txt = _clean_text(script.get_text(" ", strip=True))
        low = txt.lower()

        if not txt or len(txt) < 20:
            continue

        if any(x in low for x in ["cdb", "lci", "lca"]) and "%" in txt:
            parts = re.split(r"[{}\[\];]+", txt)
            for part in parts:
                p = _clean_text(part)
                pl = p.lower()
                if p and any(x in pl for x in ["cdb", "lci", "lca"]) and "%" in p:
                    candidates.append(p)

    # 3) Fallback no texto geral da página
    full_text = _clean_text(soup.get_text(" ", strip=True))
    windows = re.findall(
        r"(.{0,120}(?:cdb|lci|lca).{0,220})",
        full_text,
        flags=re.IGNORECASE,
    )
    candidates.extend([_clean_text(w) for w in windows if _clean_text(w)])

    return candidates


def collect():
    results = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            page = browser.new_page(viewport={"width": 1400, "height": 3000})

            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(7000)

            # rolagem para carregar conteúdo lazy/infinito
            for _ in range(8):
                page.mouse.wheel(0, 5000)
                page.wait_for_timeout(1800)

            html = page.content()
            browser.close()

        candidate_texts = _extract_candidate_blocks_from_html(html)

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

        return results

    except Exception as e:
        print(f"[YUBB ERROR] {e}")
        return []
