import re


def extract_cdi(text):
    m = re.search(r'(\d{2,3})\s*%.*cdi', text.lower())
    if m:
        return float(m.group(1))
    return None
