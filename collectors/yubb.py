import re
import requests
from bs4 import BeautifulSoup

from utils.bank_detector import detect_bank


URL = "https://yubb.com.br/investimentos/renda-fixa"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}


def _clean_text(text):
    return re.sub(r"\s+", " ", (text or "")).strip()


def _slug_to_text(slug):
    text = slug.replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text.title()


def _extract_type(text):
    text_low = (text or "").lower()

    if "lci" in text_low:
        return "LCI"
    if "lca" in text_low:
        return "LCA"
    if "cdb" in text_low:
        return "CDB"

    return None


def _extract_days(text):
    if not text:
        return 365

    match = re.search(r"(\d{1,5})-dias", text, re.I)
    if match:
        try:
            return int(match.group(1))
        except Exception:
            return 365

    match = re.search(r"(\d{1,5})\s+dias", text, re.I)
    if match:
        try:
            return int(match.group(1))
        except Exception:
            return 365

    return 365


def _extract_cdi_rate(text):
    """
    Aceita formatos como:
    - 139-cdi
    - 121-25-cdi
    - 102 cdi
    """
    if not text:
        return None

    match = re.search(r"(\d{1,3}(?:-\d{1,2})?)\s*[- ]cdi\b", text, re.I)
    if not match:
        return None

    raw = match.group(1)
    try:
        return float(raw.replace("-", "."))
    except Exception:
        return None


def _extract_liquidity(text):
    text_low = (text or "").lower()
    return "liquidez-diaria" in text_low or "liquidez diária" in text_low or "liquidez diaria" in text_low


def _guess_bank(text, slug):
    # 1) tenta detectar pelo texto visível + slug
    bank = detect_bank(f"{text} {slug}")
    if bank != "Mercado":
        return bank

    # 2) tenta inferir pelos primeiros tokens do slug antes da taxa/tipo
    parts = [p for p in slug.split("-") if p]

    stop_tokens = {
        "cdi", "ipca", "prefixado", "cdb", "lci", "lca",
        "dias", "minimo"
    }

    collected = []
    for part in parts:
        if part.isdigit():
            break
        if part in stop_tokens:
            break
        # para quando começa a parte obviamente comercial/distribuidor
        if part in {"xp", "btg", "pactual", "rico", "orama", "guide", "nu", "nubank", "agora"}:
            break
        collected.append(part)

    if not collected:
        return "Mercado"

    guess = " ".join(collected).strip()
    guess = _slug_to_text(guess)

    if len(guess) > 40:
        return "Mercado"

    return guess or "Mercado"


def collect():
    results = []
    seen = set()

    try:
        response = requests.get(URL, headers=HEADERS, timeout=20)
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        anchors = soup.find_all("a", href=True)

        for anchor in anchors:
            href = (anchor.get("href") or "").strip()
            if not href:
                continue

            if "/investimentos/renda-fixa/" not in href:
                continue

            full_url = href if href.startswith("http") else f"https://yubb.com.br{href}"
            slug = full_url.rstrip("/").split("/")[-1]

            # ignora a página-listagem
            if slug == "renda-fixa":
                continue

            visible_text = _clean_text(anchor.get_text(" ", strip=True))
            title_text = _clean_text(anchor.get("title", ""))
            aria_text = _clean_text(anchor.get("aria-label", ""))

            combined = " | ".join(
                [part for part in [visible_text, title_text, aria_text, slug] if part]
            )

            inv_type = _extract_type(combined)
            if not inv_type:
                continue

            rate = _extract_cdi_rate(slug) or _extract_cdi_rate(combined)
            if rate is None:
                # ignora prefixados/IPCA nesta fase para não misturar com % CDI
                continue

            days = _extract_days(slug)
            liquidity = _extract_liquidity(combined)
            bank = _guess_bank(visible_text or title_text or aria_text, slug)

            item = {
                "bank": bank,
                "type": inv_type,
                "rate": float(rate),
                "days": int(days),
                "liquidity": bool(liquidity),
                "source": "Yubb",
                "url": full_url,
            }

            key = (
                item["bank"],
                item["type"],
                item["rate"],
                item["days"],
                item["liquidity"],
            )

            if key in seen:
                continue

            seen.add(key)
            results.append(item)

    except Exception:
        return []

    return results
