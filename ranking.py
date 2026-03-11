from utils.calc import gross_return, net_return
from config import CDI, SELIC


def score(item):
    s = 0

    if item["rate"] >= 120:
        s += 5
    elif item["rate"] >= 110:
        s += 4
    elif item["rate"] >= 105:
        s += 3

    if item["liquidity"]:
        s += 1

    return s


def rank(data):
    for d in data:
        gross = gross_return(d["rate"], CDI)
        net = net_return(gross, d["days"])

        d["gross"] = gross
        d["net"] = net
        d["score"] = score(d)
        d["beats_selic"] = net > SELIC

    return sorted(data, key=lambda x: x["score"], reverse=True)
