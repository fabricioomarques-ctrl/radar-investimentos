from utils.calc import gross_return, net_return
from config import CDI, SELIC


def normalize_type(value):
    text = str(value or "").strip().lower()

    if "lci" in text:
        return "LCI"
    if "lca" in text:
        return "LCA"
    if "cdb" in text:
        return "CDB"

    # Fontes que retornam faixas como:
    # "Até 180 dias", "De 181 a 360 dias", etc.
    if "dias" in text or "meses" in text or "anos" in text:
        return "CDB"

    return str(value or "").strip().upper() or "INVESTIMENTO"


def classify(score):
    if score >= 11:
        return "🔴 OPORTUNIDADE IMPERDÍVEL"
    elif score >= 8:
        return "🟡 OPORTUNIDADE FORTE"
    elif score >= 5:
        return "🟢 BOA OPORTUNIDADE"
    return "⚪ OPORTUNIDADE PADRÃO"


def rare_opportunity(item, net=None):
    inv_type = normalize_type(item.get("type"))
    rate = float(item.get("rate", 0))
    liquidity = bool(item.get("liquidity", False))
    days = int(item.get("days", 365))

    # Regras mais reais para oportunidades raras
    if inv_type == "CDB":
        if liquidity and rate >= 108:
            return True
        if not liquidity and rate >= 120:
            return True
        if net is not None and net >= SELIC + 1.0:
            return True

    if inv_type in ["LCI", "LCA"]:
        if rate >= 95:
            return True
        if days <= 365 and rate >= 92:
            return True

    return False


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


def score(item, net):
    inv_type = normalize_type(item.get("type"))
    rate = float(item.get("rate", 0))
    liquidity = bool(item.get("liquidity", False))
    days = int(item.get("days", 365))
    best_rate = bool(item.get("best_rate", False))

    s = 0

    # Taxa
    if inv_type in ["LCI", "LCA"]:
        if rate >= 97:
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

    # Liquidez
    if liquidity:
        s += 1.5

    # Prazo
    if days <= 180:
        s += 1.5
    elif days <= 365:
        s += 1
    elif days <= 720:
        s += 0.5

    # Melhor que Selic
    if net >= SELIC + 1.0:
        s += 3
    elif net > SELIC + 0.25:
        s += 2
    elif net >= SELIC - 0.25:
        s += 1

    # Bônus raro
    if rare_opportunity(item, net):
        s += 2.5

    # Melhor taxa da categoria
    if best_rate:
        s += 2

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
        item["rare"] = rare_opportunity(item, net)

        items.append(item)

    items = mark_best_rates(items)

    for item in items:
        item["score"] = score(item, item["net"])
        item["beats_selic"] = item["net"] > SELIC
        item["classification"] = classify(item["score"])

    return sorted(
        items,
        key=lambda x: (
            x.get("rare", False),
            x.get("best_rate", False),
            x.get("beats_selic", False),
            x.get("score", 0),
            x.get("net", 0),
            x.get("rate", 0)
        ),
        reverse=True
    )
