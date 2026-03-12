import re
import json
import requests
from playwright.sync_api import sync_playwright

PAGE_URL = "https://yubb.com.br/investimentos/renda-fixa"
API_CANDIDATES = [
    "https://api.yubb.com.br/investments/fixed-income",
    "https://api.yubb.com.br/investments/fixed-income/",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
        "Mobile/15E148 Safari/604.1"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": PAGE_URL,
}


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).strip()
        text = text.replace("%", "").replace(",", ".")
        match = re.search(r"(\d+(?:\.\d+)?)", text)
        if match:
            return float(match.group(1))
        return default
    except Exception:
        return default


def _safe_int(value, default=365):
    try:
        if value is None:
            return default
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)

        text = str(value).strip().lower().replace(",", ".")
        m_days = re.search(r"(\d+)\s*dias?", text)
        if m_days:
            return int(m_days.group(1))

        m_months = re.search(r"(\d+)\s*meses?", text)
        if m_months:
            return int(m_months.group(1)) * 30

        m_years = re.search(r"(\d+)\s*anos?", text)
        if m_years:
            return int(m_years.group(1)) * 365

        match = re.search(r"(\d+)", text)
        if match:
            return int(match.group(1))

        return default
    except Exception:
        return default


def _safe_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False

    text = str(value).strip().lower()
    return text in {"1", "true", "sim", "yes", "y", "daily", "liquidez diária", "liquidez diaria"}


def _detect_type(item):
    candidates = [
        item.get("type"),
        item.get("product_type"),
        item.get("investment_type"),
        item.get("kind"),
        item.get("name"),
        item.get("title"),
        item.get("product"),
        item.get("categoria"),
    ]

    joined = " ".join(str(x) for x in candidates if x).lower()

    if "lci" in joined:
        return "LCI"
    if "lca" in joined:
        return "LCA"
    if "cdb" in joined:
        return "CDB"
    if "lc " in joined or joined == "lc":
        return "LC"
    return str(item.get("type") or item.get("product_type") or "CDB").upper()


def _detect_bank(item):
    bank = (
        item.get("bank")
        or item.get("bank_name")
        or item.get("institution")
        or item.get("institution_name")
        or item.get("issuer")
        or item.get("emissor")
        or item.get("company")
        or "Banco"
    )
    return str(bank).strip()


def _detect_rate(item):
    for key in [
        "rate", "profitability", "yield", "return", "taxa", "percent", "percentage"
    ]:
        if key in item and item.get(key) not in (None, ""):
            return _safe_float(item.get(key), 100.0)

    text_candidates = [
        item.get("name"),
        item.get("title"),
        item.get("description"),
        item.get("subtitle"),
    ]
    for text in text_candidates:
        rate = _safe_float(text, None)
        if rate is not None:
            return rate

    return 100.0


def _detect_days(item):
    for key in [
        "term", "days", "duration", "term_days", "prazo", "maturity_days"
    ]:
        if key in item and item.get(key) not in (None, ""):
            return _safe_int(item.get(key), 365)

    text_candidates = [
        item.get("name"),
        item.get("title"),
        item.get("description"),
        item.get("subtitle"),
    ]
    for text in text_candidates:
        days = _safe_int(text, None)
        if days is not None:
            return days

    return 365


def _detect_liquidity(item):
    for key in [
        "liquidity", "daily_liquidity", "has_daily_liquidity",
        "rescue_daily", "liquidez", "liquidez_diaria"
    ]:
        if key in item:
            return _safe_bool(item.get(key))

    text_candidates = [
        str(item.get("name", "")),
        str(item.get("title", "")),
        str(item.get("description", "")),
        str(item.get("subtitle", "")),
    ]
    joined = " ".join(text_candidates).lower()
    if "liquidez diária" in joined or "liquidez diaria" in joined or "resgate diário" in joined:
        return True

    return False


def _normalize_item(item):
    try:
        normalized = {
            "bank": _detect_bank(item),
            "type": _detect_type(item),
            "rate": _detect_rate(item),
            "days": _detect_days(item),
            "liquidity": _detect_liquidity(item),
            "source": "Yubb",
            "url": PAGE_URL,
        }

        if not normalized["bank"]:
            return None
        if normalized["rate"] <= 0:
            return None
        if normalized["days"] <= 0:
            normalized["days"] = 365

        return normalized
    except Exception:
        return None


def _deduplicate(results):
    seen = set()
    unique = []

    for item in results:
        key = (
            item.get("bank"),
            item.get("type"),
            item.get("rate"),
            item.get("days"),
            item.get("liquidity"),
        )
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique


def _extract_candidates_from_json(data):
    """
    Percorre recursivamente qualquer JSON e tenta achar objetos que pareçam
    investimentos de renda fixa.
    """
    found = []

    def walk(node):
        if isinstance(node, dict):
            keys = {str(k).lower() for k in node.keys()}

            signal_keys = {
                "bank", "bank_name", "institution", "issuer",
                "type", "product_type", "investment_type",
                "rate", "profitability", "yield",
                "term", "days", "duration", "prazo",
                "liquidity", "daily_liquidity", "liquidez"
            }

            if keys & signal_keys:
                found.append(node)

            for value in node.values():
                walk(value)

        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return found


def _collect_via_direct_api():
    results = []

    for api_url in API_CANDIDATES:
        try:
            r = requests.get(api_url, headers=HEADERS, timeout=20)
            if r.status_code != 200:
                continue

            data = r.json()
            candidates = _extract_candidates_from_json(data)

            for item in candidates:
                normalized = _normalize_item(item)
                if normalized:
                    results.append(normalized)

            results = _deduplicate(results)
            if results:
                return results

        except Exception:
            continue

    return results


def _collect_via_playwright_network():
    captured_json_payloads = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=HEADERS["User-Agent"])

            def handle_response(response):
                try:
                    ctype = response.headers.get("content-type", "").lower()
                    url = response.url.lower()

                    if "application/json" not in ctype:
                        return

                    interesting = any(token in url for token in [
                        "api.yubb",
                        "investment",
                        "fixed-income",
                        "renda-fixa",
                        "products",
                        "product"
                    ])

                    if not interesting:
                        return

                    data = response.json()
                    captured_json_payloads.append(data)
                except Exception:
                    pass

            page.on("response", handle_response)
            page.goto(PAGE_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(8000)

            # tentativa extra: buscar JSON embutido no HTML
            html = page.content()
            browser.close()

        results = []

        for payload in captured_json_payloads:
            candidates = _extract_candidates_from_json(payload)
            for item in candidates:
                normalized = _normalize_item(item)
                if normalized:
                    results.append(normalized)

        # fallback extra: tentar pegar __NEXT_DATA__ ou JSON embutido
        if not results and html:
            scripts = re.findall(
                r'<script[^>]*type="application/json"[^>]*>(.*?)</script>',
                html,
                flags=re.S | re.I
            )

            for raw in scripts:
                try:
                    data = json.loads(raw)
                    candidates = _extract_candidates_from_json(data)
                    for item in candidates:
                        normalized = _normalize_item(item)
                        if normalized:
                            results.append(normalized)
                except Exception:
                    continue

        return _deduplicate(results)

    except Exception:
        return []


def collect():
    """
    Estratégia:
    1) tenta API direta com headers
    2) se vier vazio, tenta Playwright capturando JSON da página
    """
    results = _collect_via_direct_api()

    if results:
        return results

    results = _collect_via_playwright_network()

    if results:
        return results

    return []
