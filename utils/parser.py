import re


KNOWN_BANKS = [
    "Inter",
    "BTG",
    "BTG Pactual",
    "XP",
    "XP Investimentos",
    "Rico",
    "Órama",
    "Orama",
    "Genial",
    "Daycoval",
    "Sofisa",
    "Pan",
    "BMG",
    "BV",
    "Itaú",
    "Itau",
    "Bradesco",
    "Santander",
    "Caixa",
    "PagBank",
    "PicPay",
    "Mercado Pago",
]


def extract_cdi(text):
    low = text.lower()

    patterns = [
        r'(\d{2,3}(?:[.,]\d{1,2})?)\s*%\s*(?:do\s*)?cdi',
        r'(\d{2,3}(?:[.,]\d{1,2})?)\s*%'
    ]

    for pattern in patterns:
        m = re.search(pattern, low)
        if m:
            raw = m.group(1).replace(",", ".")
            try:
                value = float(raw)
                if 70 <= value <= 200:
                    return value
            except Exception:
                pass

    return None


def extract_product_type(text):
    low = text.lower()

    if "lci" in low:
        return "LCI"
    if "lca" in low:
        return "LCA"
    if "cdb" in low:
        return "CDB"

    return None


def extract_bank(text):
    for bank in KNOWN_BANKS:
        if bank.lower() in text.lower():
            return bank
    return None


def extract_term_days(text):
    low = text.lower()

    m = re.search(r'(\d{1,2})\s*mes(?:es)?', low)
    if m:
        return int(m.group(1)) * 30

    y = re.search(r'(\d{1,2})\s*ano(?:s)?', low)
    if y:
        return int(y.group(1)) * 365

    d = re.search(r'(\d{2,4})\s*dias?', low)
    if d:
        return int(d.group(1))

    if "liquidez diária" in low or "liquidez diaria" in low:
        return 1

    return 365


def extract_liquidity(text):
    low = text.lower()
    return "liquidez diária" in low or "liquidez diaria" in low
