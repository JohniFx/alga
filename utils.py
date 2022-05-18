import cfg
from datetime import datetime


def get_now():
    return datetime.now().strftime('%H:%M:%S')


def get_position_tradeIDs(inst: str) -> list:
    for p in cfg.account.positions:
        if p.instrument == inst:
            if p.long.tradeIDs:
                return p.long.tradeIDs
            if p.short.tradeIDs:
                return p.short.tradeIDs
    return None
