import re


BANK_PATTERNS = {
    "Inter": [r"\binter\b", r"\bbanco inter\b"],
    "Pan": [r"\bpan\b", r"\bbanco pan\b"],
    "BMG": [r"\bbmg\b"],
    "Sofisa": [r"\bsofisa\b"],
    "Daycoval": [r"\bdaycoval\b"],
    "BTG Pactual": [r"\bbtg\b", r"\bbtg pactual\b"],
    "XP": [r"\bxp\b", r"\bxp investimentos\b"],
    "Rico": [r"\brico\b"],
    "Ágora": [r"\bagora\b", r"\bágora\b"],
    "Órama": [r"\borama\b", r"\bórama\b"],
    "Guide": [r"\bguide\b"],
    "Nubank": [r"\bnu\b", r"\bnubank\b"],
    "Original": [r"\boriginal\b"],
    "Fibra": [r"\bfibra\b"],
    "Máxima": [r"\bmaxima\b", r"\bmáxima\b"],
    "Banco Industrial do Brasil": [r"\bbanco industrial do brasil\b"],
    "Mercantil": [r"\bmercantil\b"],
    "ABC Brasil": [r"\babc brasil\b"],
    "Pine": [r"\bpine\b"],
}


def detect_bank(text: str) -> str:
    if not text:
        return "Mercado"

    normalized = text.lower()

    for bank, patterns in BANK_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, normalized):
                return bank

    return "Mercado"
