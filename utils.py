import cfg
from datetime import datetime
import v20
import threading

insts = []


def run_threaded(job_func, args=[]):
    t = threading.Thread(target=job_func, args=args)
    t.start()


def get_now():
    return datetime.now().strftime('%H:%M:%S')


def get_trade_info(t: v20.trade.Trade) -> str:
    msg = f'{t.id:>8}'
    msg += f'{t.instrument:>8}'
    msg += f'{t.currentUnits:>6.0f}'
    msg += f'{t.unrealizedPL:>7.2f}'
    msg += f'{t.price:>10.4f}'
    if t.stopLossOrder is None:
        nsm = 'NO STOP'
        msg += f'{nsm:>10}'
        msg += ' **NO STOP** '
    else:
        msg += f'{t.stopLossOrder.price:>10.4f}'

    if t.trailingStopLossOrder is None:
        nts = 'NO TS'
        msg += f'{nts:>8}'
    else:
        msg += f'{t.trailingStopLossOrder.distance:>8.4f}'

    msg += f'{t.marginUsed:>8.2f}'

    if t.currentUnits > 0:
        if t.stopLossOrder.price >= t.price:
            msg = '{} {}'.format(msg, '*')
    if t.currentUnits < 0:
        if t.stopLossOrder.price <= t.price:
            msg = '{} {}'.format(msg, '*')

    return msg


def get_position_info(p):
    msg = (f'{p.instrument:>7}'
           f'{p.unrealizedPL:>7.2f} ')
    if p.long.units > 0:
        # tradeIDs:{p.long.tradeIDs}'
        msg += f'units:{p.long.units}  avp:{p.long.averagePrice}'
    if p.short.units < 0:
        # tradeIDs:{p.short.tradeIDs}'
        msg += f'units:{p.short.units} avp:{p.short.averagePrice}'
    return msg


def get_trade_by_id(tradeid: int) -> v20.trade.TradeSummary:
    for t in cfg.account.trades:
        if t.id == tradeid:
            return t


def get_order_by_id(orderid: int) -> v20.order.Order:
    # itt cfg.account.order is a v20.trade.TradeSummary
    for o in cfg.account.orders:
        if o.id == orderid:
            return o


def get_position_tradeIDs(inst: str) -> list:
    for p in cfg.account.positions:
        if p.instrument == inst:
            if p.long.tradeIDs:
                return p.long.tradeIDs
            if p.short.tradeIDs:
                return p.short.tradeIDs
    return None
