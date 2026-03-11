def get_fallback():
    return [
        {
            "bank": "Simulação Interna",
            "type": "CDB",
            "rate": 110,
            "days": 365,
            "liquidity": False
        },
        {
            "bank": "Simulação Interna",
            "type": "CDB",
            "rate": 102,
            "days": 1,
            "liquidity": True
        },
        {
            "bank": "Simulação Interna",
            "type": "LCI",
            "rate": 92,
            "days": 365,
            "liquidity": False
        }
    ]
