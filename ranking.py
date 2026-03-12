from utils.calc import gross_return, net_return
from config import CDI, SELIC


def classify(score):

    if score >= 10:
        return "🔥 OPORTUNIDADE EXCEPCIONAL"

    if score >= 8:
        return "🟡 OPORTUNIDADE FORTE"

    if score >= 5:
        return "🟢 BOA OPORTUNIDADE"

    return "⚪ OPORTUNIDADE PADRÃO"


def detect_market_average(data):

    if not data:
        return 0

    rates = [i["rate"] for i in data]

    return sum(rates) / len(rates)


def detect_anomaly(rate, market_avg):

    if market_avg == 0:
        return False

    if rate >= market_avg + 10:
        return True

    return False


def rare_opportunity(item, net):

    rate = item["rate"]

    if item["type"] == "CDB":

        if item["liquidity"] and rate >= 108:
            return True

        if not item["liquidity"] and rate >= 120:
            return True

    if item["type"] in ["LCI", "LCA"] and rate >= 95:
        return True

    if net > SELIC + 1.5:
        return True

    return False


def score(item, net, market_avg):

    s = 0

    rate = item["rate"]

    if rate >= market_avg + 10:
        s += 4

    elif rate >= market_avg + 5:
        s += 3

    elif rate >= market_avg + 2:
        s += 2

    elif rate >= market_avg:
        s += 1

    if item["liquidity"]:
        s += 1

    if item["days"] <= 365:
        s += 1

    if net > SELIC:
        s += 2

    if item.get("rare"):
        s += 2

    if item.get("best_rate"):
        s += 2

    return round(s, 1)


def mark_best_rates(data):

    best_rate = 0

    for i in data:

        if i["rate"] > best_rate:
            best_rate = i["rate"]

    for i in data:

        if i["rate"] == best_rate:
            i["best_rate"] = True
        else:
            i["best_rate"] = False

    return best_rate


def rank(data):

    market_avg = detect_market_average(data)

    best_rate = mark_best_rates(data)

    for d in data:

        gross = gross_return(d["rate"], CDI)

        net = net_return(gross, d["days"])

        d["gross"] = gross
        d["net"] = net

        d["rare"] = rare_opportunity(d, net)

        d["anomaly"] = detect_anomaly(d["rate"], market_avg)

        d["score"] = score(d, net, market_avg)

        d["beats_selic"] = net > SELIC

        d["classification"] = classify(d["score"])

    return sorted(
        data,
        key=lambda x: (x["score"], x["rate"]),
        reverse=True
    )
