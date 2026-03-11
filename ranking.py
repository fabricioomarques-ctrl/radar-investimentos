from utils.calc import gross_return, net_return
from config import CDI, SELIC


def classify(score):
    if score >= 9:
        return "🔴 OPORTUNIDADE IMPERDÍVEL"
    elif score >= 7:
        return "🟡 OPORTUNIDADE FORTE"
    elif score >= 5:
        return "🟢 BOA OPORTUNIDADE"
    return "⚪ OPORTUNIDADE PADRÃO"


def score(item, net):
    s = 0

    # Taxa
    if item["type"] in ["LCI", "LCA"]:
        if item["rate"] >= 97:
            s += 5
        elif item["rate"] >= 95:
            s += 4
        elif item["rate"] >= 92:
            s += 3
        elif item["rate"] >= 90:
            s += 2
    else:
        if item["rate"] >= 120:
            s += 6
        elif item["rate"] >= 115:
            s += 5
        elif item["rate"] >= 110:
            s += 4
        elif item["rate"] >= 105:
            s += 3
        elif item["rate"] >= 102:
            s += 2

    # Liquidez
    if item["liquidity"]:
        s += 1

    # Prazo
    if item["days"] <= 365:
        s += 1
    elif item["days"] <= 720:
        s += 0.5

    # Melhor que Selic
    if net > SELIC:
        s += 2
    elif net >= SELIC - 0.5:
        s += 1

    return round(s, 1)


def rank(data):
    for d in data:
        gross = gross_return(d["rate"], CDI)
        net = net_return(gross, d["days"])

        d["gross"] = gross
        d["net"] = net
        d["score"] = score(d, net)
        d["beats_selic"] = net > SELIC
        d["classification"] = classify(d["score"])

    return sorted(
        data,
        key=lambda x: (x["score"], x["net"]),
        reverse=True
    )
