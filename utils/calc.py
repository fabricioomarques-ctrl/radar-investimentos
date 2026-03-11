def gross_return(rate_cdi, cdi):
    return (rate_cdi / 100) * cdi


def net_return(gross, days):
    if days <= 180:
        ir = 0.225
    elif days <= 360:
        ir = 0.20
    elif days <= 720:
        ir = 0.175
    else:
        ir = 0.15

    return gross * (1 - ir)
