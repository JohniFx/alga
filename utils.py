from datetime import datetime
import pickle
import defs
import v20
import threading

insts = []

def run_threaded(job_func, args=[]):
    t = threading.Thread(target=job_func, args=args)
    t.start()

def get_instruments(ctx, accountid):
    insts = ctx.account.instruments(accountid).get('instruments')
    return insts


def save_instruments(insts):
    with open('insts.pkl', 'wb') as handle:
        pickle.dump(inst, handle)


def load_instruments():
    with open('insts.pkl', 'rb') as handle:
        insts = pickle.load(handle)
    return insts


def get_piplocation(name: str, insts: list):
    for i in insts:
        if i.name == name:
            return pow(10, i.pipLocation)
    return None


def get_displayprecision(name: str, insts: list):
    for i in insts:
        if i.name == name:
            return i.displayPrecision
    return None


def get_instrument(name: str, insts: list) -> v20.primitives.Instrument:
    for i in insts:
        if i.name == name:
            return i
    return None


def get_now():
    return datetime.now().strftime('%H:%M:%S')


def get_account_info(ac):
    msg = (f' {get_now()} '
           f' NAV:{ac.NAV:.2f}'
           f' PNL:{ac.unrealizedPL:.2f}')
    return msg


def get_trade_info(t: v20.trade.Trade) -> str:
    msg = f'{t.id:>8}'
    msg += f'{t.instrument:>8}'
    msg += f'{t.currentUnits:>6.0f}'
    msg += f'{t.unrealizedPL:>7.2f}'
    msg += f'{t.price:>10.4f}'
    if t.stopLossOrder is None:
        nsm = 'NO STOP'
        msg += f'{nsm:>10}'
        msg += f' **NO STOP** '
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


def get_trades_by_instrument(trades, instrument):
    inst_trades = []
    for t in trades:
        if t.instrument == instrument:
            inst_trades.append(t)
    return inst_trades


def check_breakeven_for_position(trades, instrument):
    # print('breakevencheck: ', instrument)
    all_breakeven = []
    for t in trades:
        if t.instrument == instrument:
            all_breakeven.append(
                (t.currentUnits > 0 and t.stopLossOrder.price >= t.price)
                or
                (t.currentUnits < 0 and t.stopLossOrder.price <= t.price))
    # print('len(trades)', all_breakeven)
    return all(all_breakeven)


if __name__ == "__main__":
    #Testing util functions
    import v20
    import defs
    ctx = v20.Context(hostname=defs.HOSTNAME, token=defs.key)
    ctx.set_header(key='Authorization', value=defs.key)
    inst = get_instruments(ctx, defs.ACCOUNT_ID)
    save_instruments(insts)
