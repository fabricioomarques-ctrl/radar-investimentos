import re
import requests
from bs4 import BeautifulSoup

URL = "https://statusinvest.com.br"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/145.0.0.0 Safari/537.36"
    )
}


def _safe_float(text, default=None):
    try:
        if text is None:
            return default

        cleaned = str(text).replace("%", "").replace(",", ".").strip()
        match = re.search(r"(\d+(?:\.\d+)?)", cleaned)

        if match:
            return float(match.group(1))

        return default
    except Exception:
        return default


def _safe_int(text, default=365):
    try:
        if text is None:
            return default

        base = str(text).lower().strip()

        m_days = re.search(r"(\d+)\s*dias?", base)
        if m_days:
            return int(m_days.group(1))

        m_months = re.search(r"(\d+)\s*meses?", base)
        if m_months:
            return int(m_months.group(1)) * 30

        m_years = re.search(r"(\d+)\s*anos?", base)
        if m_years:
            return int(m_years.group(1)) * 365

        match = re.search(r"(\d+)", base)
        if match:
            return int(match.group(1))

        return default
    except Exception:
        return default


def _detect_type(text):
    base = str(text).lower()

    if "lci" in base:
        return "LCI"
    if "lca" in base:
        return "LCA"
    if "cdb" in base:
        return "CDB"

    return None


def collect():
    results = []

    try:
        r = requests.get(URL, headers=HEADERS, timeout=20)

        if r.status_code != 200:
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        blocks = soup.find_all(["div", "article", "section", "li", "span"])

        for block in blocks:
            text = block.get_text(" ", strip=True)

            if not text:
                continue

            text_lower = text.lower()

            if not any(k in text_lower for k in ["cdb", "lci", "lca"]):
                continue

            rate = None

            rate_cdi = re.search(r"(\d+(?:[.,]\d+)?)\s*%\s*cdi", text, re.I)
            if rate_cdi:
                rate = _safe_float(rate_cdi.group(1))

            if rate is None:
                continue

            inv_type = _detect_type(text)
            if not inv_type:
                continue

            liquidity = any(
                k in text_lower for k in [
                    "liquidez diária",
                    "liquidez diaria",
                    "resgate diário",
                    "resgate diario"
                ]
            )

            days = _safe_int(text, 365)

            results.append({
                "bank": "Mercado",
                "type": inv_type,
                "rate": rate,
                "days": days,
                "liquidity": liquidity,
                "source": "StatusInvest",
                "url": URL
            })

    except Exception:
        return []

    return results
