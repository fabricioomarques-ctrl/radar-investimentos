from utils.calc import gross_return, net_return
from config import CDI, SELIC


PROMO_CDB_RATE = 120.0
PROMO_ISENTO_RATE = 97.0

ANOMALY_GAP_CDB = 8.0
ANOMALY_GAP_ISENTO = 5.0


def normalize_type(value):
    text = str(value or "").strip().lower()

    if "lci" in text:
        return "LCI"
    if "lca" in text:
        return "LCA"
    if "cdb" in text:
        return "CDB"

    if "dias" in text or "meses" in text or "anos" in text:
        return "CDB"

    return str(value or "").strip().upper() or "INVESTIMENTO"


def classify(score):
    if score >= 13:
        return "🔴 OPORTUNIDADE IMPERDÍVEL"
    elif score >= 9:
        return "🟡 OPORTUNIDADE FORTE"
    elif score >= 5:
        return "🟢 BOA OPORTUNIDADE"
    return "⚪ OPORTUNIDADE PADRÃO"


def build_market_averages(items):
    groups = {}

    for item in items:
        inv_type = item.get("type_normalized")
        rate = float(item.get("rate", 0))

        if inv_type not in groups:
            groups[inv_type] = []

        groups[inv_type].append(rate)

    averages = {}

    for inv_type, rates in groups.items():
        if rates:
            averages[inv_type] = round(sum(rates) / len(rates), 2)
        else:
            averages[inv_type] = 0

    return averages


def mark_best_rates(items):
    best_by_type = {}

    for item in items:
        inv_type = item.get("type_normalized")
        rate = float(item.get("rate", 0))

        if inv_type not in best_by_type or rate > best_by_type[inv_type]:
            best_by_type[inv_type] = rate

    for item in items:
        inv_type = item.get("type_normalized")
        item["best_rate"] = float(item.get("rate", 0)) == best_by_type.get(inv_type, -1)

    return items


def detect_promo(item, net=None):
    inv_type = item.get("type_normalized") or normalize_type(item.get("type"))
    rate = float(item.get("rate", 0))

    if inv_type == "CDB" and rate >= PROMO_CDB_RATE:
        return True

    if inv_type in ["LCI", "LCA"] and rate >= PROMO_ISENTO_RATE:
        return True

    if net is not None and net >= SELIC + 1.5:
        return True

    return False


def detect_anomaly(item, market_avg):
    inv_type = item.get("type_normalized") or normalize_type(item.get("type"))
    rate = float(item.get("rate", 0))

    if market_avg <= 0:
        return False

    if inv_type == "CDB" and rate >= market_avg + ANOMALY_GAP_CDB:
        return True

    if inv_type in ["LCI", "LCA"] and rate >= market_avg + ANOMALY_GAP_ISENTO:
        return True

    return False


def score(item, net):
    inv_type = item.get("type_normalized") or normalize_type(item.get("type"))
    rate = float(item.get("rate", 0))
    liquidity = bool(item.get("liquidity", False))
    days = int(item.get("days", 365))
    best_rate = bool(item.get("best_rate", False))
    promo = bool(item.get("promo", False))
    anomaly = bool(item.get("anomaly", False))
    above_bank_history = bool(item.get("above_bank_history", False))
    above_type_history = bool(item.get("above_type_history", False))
    best_recent_level = bool(item.get("best_recent_level", False))

    s = 0

    if inv_type in ["LCI", "LCA"]:
        if rate >= 100:
            s += 7
        elif rate >= 97:
            s += 6
        elif rate >= 95:
            s += 5
        elif rate >= 92:
            s += 4
        elif rate >= 90:
            s += 3
        elif rate >= 85:
            s += 2
    else:
        if rate >= 125:
            s += 8
        elif rate >= 120:
            s += 7
        elif rate >= 115:
            s += 6
        elif rate >= 110:
            s += 5
        elif rate >= 105:
            s += 4
        elif rate >= 102:
            s += 2

    if liquidity:
        s += 1.5

    if days <= 180:
        s += 1.5
    elif days <= 365:
        s += 1
    elif days <= 720:
        s += 0.5

    if net >= SELIC + 1.0:
        s += 3
    elif net > SELIC + 0.25:
        s += 2
    elif net >= SELIC - 0.25:
        s += 1

    if best_rate:
        s += 1.5

    if promo:
        s += 3

    if anomaly:
        s += 2.5

    if above_bank_history:
        s += 1.5

    if above_type_history:
        s += 1.5

    if best_recent_level:
        s += 1.0

    return round(s, 1)


def rank(data):
    items = []

    for item in data:
        item["type_normalized"] = normalize_type(item.get("type"))

        gross = gross_return(item["rate"], CDI)

        if item["type_normalized"] in ["LCI", "LCA"]:
            net = gross
        else:
            net = net_return(gross, item["days"])

        item["gross"] = gross
        item["net"] = net
        items.append(item)

    items = mark_best_rates(items)
    market_averages = build_market_averages(items)

    for item in items:
        inv_type = item["type_normalized"]
        item["market_avg"] = market_averages.get(inv_type, 0)
        item["promo"] = detect_promo(item, item["net"])
        item["anomaly"] = detect_anomaly(item, item["market_avg"])
        item["beats_selic"] = item["net"] > SELIC
        item["score"] = score(item, item["net"])
        item["classification"] = classify(item["score"])

    return sorted(
        items,
        key=lambda x: (
            x.get("promo", False),
            x.get("anomaly", False),
            x.get("above_bank_history", False),
            x.get("above_type_history", False),
            x.get("best_recent_level", False),
            x.get("best_rate", False),
            x.get("beats_selic", False),
            x.get("score", 0),
            x.get("net", 0),
            x.get("rate", 0)
        ),
        reverse=True
    )
