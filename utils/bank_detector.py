import re

BANK_PATTERNS = {
    "Inter": ["inter"],
    "Pan": ["pan"],
    "BMG": ["bmg"],
    "Sofisa": ["sofisa"],
    "Daycoval": ["daycoval"],
    "BTG": ["btg"],
    "XP": ["xp"],
    "Original": ["original"],
    "ABC": ["abc brasil"],
    "Pine": ["pine"],
    "Mercantil": ["mercantil"],
}


def detect_bank(text: str):

    if not text:
        return "Mercado"

    text = text.lower()

    for bank, patterns in BANK_PATTERNS.items():

        for p in patterns:

            if p in text:
                return bank

    return "Mercado"
