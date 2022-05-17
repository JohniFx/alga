import v20
from v20.account import AccountChanges
import threading
import time
import configparser
import json
from datetime import datetime
import utils as u
#
config = configparser.ConfigParser()
config.read('config.ini')
#
API_KEY = config['OANDA2']['API_KEY']
ACCOUNT_ID = config['OANDA2']['ACCOUNT_ID']
HOSTNAME = "api-fxpractice.oanda.com"
STREAMHOST = "stream-fxpractice.oanda.com"
key = f'Bearer {API_KEY}'
# contexts
ctx = v20.Context(hostname=HOSTNAME, token=key)
ctx.set_header(key='Authorization', value=key)
ctxs = v20.Context(hostname=STREAMHOST, token=key)
ctxs.set_header(key='Authorization', value=key)
#
account = None
lastTransactionID = 0


def restart():
    import os
    import sys
    print(f'\n{u.get_now()} RESTART')
    os.execv('./main.py', sys.argv)


def get_account():
    response = ctx.account.get(ACCOUNT_ID)
    return response.get('account')


messages = []

insts = ctx.account.instruments(ACCOUNT_ID).get('instruments')
instruments = {i.name: i.dict() for i in insts}

tradeable_instruments = [
    'EUR_USD', 'EUR_CAD', 'EUR_NZD', 'EUR_CHF', 'EUR_JPY', 'EUR_AUD', 'EUR_GBP',
    'GBP_USD', 'GBP_CAD', 'GBP_JPY', 'GBP_AUD',
    'AUD_USD', 'AUD_CAD', 'AUD_NZD', 'AUD_JPY',
    'NZD_USD', 'NZD_JPY',
    'USD_CHF', 'USD_CAD', 'USD_JPY']


# observers
price_observers = []
transaction_observers = []
account_observers = []

# TODO: kivinni jsonba és minden loopban ujratölteni
global_params = dict(
    tp=35,
    sl=13,
    ts=15,
    max_spread=3,
    be_pips=11,
    be_sl=2)


def create_stats() -> dict:
    stats = dict(
        created=str(datetime.now()),
        count_sl=0,
        count_ts=0,
        count_tp=0,
        sum_sl=0,
        sum_ts=0,
        sum_tp=0,
        count_manual=0,
        sum_manual=0
    )
    if datetime.now().hour != 7:
        try:
            f = open('stats.json', 'r')
            stats = json.load(f)
        except OSError as e:
            print('no stats yet', e)
        except json.decoder.JSONDecodeError as e:
            print('json file hiba', e, )
        print_stats(stats)
    return stats


def print_stats(stats):
    print(f"{u.get_now()} sl: {stats['count_sl']}/{stats['sum_sl']:.2f}",
          f" ts: {stats['count_ts']}/{stats['sum_ts']:.2f}",
          f" tp: {stats['count_tp']}/{stats['sum_tp']:.2f}",
          f" mt: {stats['count_manual']}/{stats['sum_manual']:.2f}")


def notify_price_observers(cp):
    for o in price_observers:
        o.on_tick(cp)


def notify_transaction_observers(data):
    for o in transaction_observers:
        o.on_data(data)


def notify_account_observers():
    for o in account_observers:
        o.on_account_changes()


def run_price_stream(tradeable_instruments: list):
    print('start price stream')
    tradeinsts = ','.join(tradeable_instruments[:20])
    response = ctxs.pricing.stream(ACCOUNT_ID, instruments=tradeinsts)
    try:
        for typ, data in response.parts():
            if typ == "pricing.ClientPrice":
                # print(f'{data.instrument} {data.bids[0].price} {data.tradeable}')
                cp = dict(
                    i=data.instrument,
                    bid=data.bids[0].price,
                    ask=data.asks[0].price)
                notify_price_observers(cp)
                instruments[data.instrument]['bid'] = data.bids[0].price
                instruments[data.instrument]['ask'] = data.asks[0].price
                instruments[data.instrument]['spread'] = round(
                    data.asks[0].price-data.bids[0].price,
                    instruments[data.instrument]['displayPrecision'])
    except ValueError as e:
        print('ValueError in pricestream', e)
    except Exception as e:
        print('Exception in price stream, RESTART', e)
        time.sleep(5)
        restart()


def run_transaction_stream():
    # print('start transaction stream')
    response = ctxs.transaction.stream(ACCOUNT_ID)
    try:
        for t, d in response.parts():
            if d.type != "HEARTBEAT":
                notify_transaction_observers(d)
    except Exception as e:
        print('Transaction stream crashed. RESTART', e)
        time.sleep(5)
        restart()


def get_piploc(inst):
    return instruments[inst]['pipLocation']


def run_account_update(account, lastTransactionID):
    print('start account polling')
    _lastId = lastTransactionID
    while True:
        try:
            account = get_account()
            # r = ctx.account.changes(ACCOUNT_ID, sinceTransactionID=_lastId)
            # changes = r.get('changes')
            # state = r.get('state')
            # _lastId = r.get('lastTransactionID')
            # update_account(account, changes, state)
            notify_account_observers()
        except Exception as e:
            print('Account update loop crashed', e)
            time.sleep(60)
            restart()
        time.sleep(30)


def update_trades(account, state):
    for st in state.trades:
        for at in account.trades:
            if at.id == st.id:
                at.unrealizedPL = st.unrealizedPL
                at.marginUsed = st.marginUsed


def update_fields(account, state):
    for field in state.fields():
        update_attribute(account, field.name, field.value)


def update_attribute(dest, name, value):
    if name in ('orders', 'trades', 'positions'):
        return
    if hasattr(dest, name) and getattr(dest, name) is not None:
        setattr(dest, name, value)


def update_positions(account, state):
    for sp in state.positions:
        for ap in account.positions:
            if ap.instrument == sp.instrument:
                ap.netUnrealizedPL = sp.netUnrealizedPL
                ap.longUnrealizedPL = sp.longUnrealizedPL
                ap.shortUnrealizedPL = sp.shortUnrealizedPL
                ap.marginUsed = sp.marginUsed


def update_orders(account, state):
    for so in state.orders:
        for o in account.orders:
            if o.id == so.id:
                o.trailingStopValue = so.trailingStopValue
                o.distance = so.triggerDistance


def apply_changes(account, changes: AccountChanges):
    for to in changes.tradesOpened:
        account.trades.append(to)
    for tr in changes.tradesReduced:
        for t in account.trades:
            if t.id == tr.id:
                t.currentUnits = tr.currentUnits
                t.realizedPL = tr.realizedPL
                t.averageClosePrice = tr.averageClosePrice

    for tc in changes.tradesClosed:
        for t in account.trades:
            if t.id == tc.id:
                account.trades.remove(t)

    for cp in changes.positions:
        for ap in account.positions:
            if ap.instrument == cp.instrument:
                account.positions.remove(ap)
                account.positions.append(cp)
                ap.unrealizedPL = 0.0

    for occ in changes.ordersCancelled:
        for o in account.orders:
            if o.id == occ.id:
                account.orders.remove(o)
                for t in account.trades:
                    if t.id == occ.tradeID:
                        if occ.type == 'STOP_LOSS':
                            t.stopLossOrderID = None
                        elif occ.type == 'TAKE_PROFIT':
                            t.takeProfitOrderID = None
                        elif occ.type == 'TRAILING_STOP_LOSS':
                            t.trailingStopLossOrderID = None

    for ocr in changes.ordersCreated:
        account.orders.append(ocr)
        for t in account.trades:
            # AttributeError: 'StopOrder' object has no attribute 'tradeID'
            if t.id == ocr.tradeID:
                if ocr.type == 'STOP_LOSS':
                    t.stopLossOrderID = ocr.id
                elif ocr.type == 'TAKE_PROFIT':
                    t.takeProfitOrderID = ocr.id
                elif ocr.type == 'TRAILING_STOP_LOSS':
                    t.trailingStopLossOrderID = ocr.id

    for ofi in changes.ordersFilled:
        for o in account.orders:
            if o.id == ofi.id:
                account.orders.remove(o)

    for otr in changes.ordersTriggered:
        for o in account.orders:
            if o.id == otr.id:
                account.orders.remove(o)


def update_account(account, changes, state):
    apply_changes(account, changes)
    update_fields(account, state)
    update_trades(account, state)
    update_positions(account, state)
    update_orders(account, state)


def print_account():
    ac = account
    print(f"{u.get_now()}",
          f"BAL: {float(ac.balance):6.0f}",
          f"NAV: {float(ac.NAV):>7.2f}",
          f"pl:{float(ac.unrealizedPL):>6.2f}",
          f"t:{ac.openTradeCount}",
          f"o:{ac.pendingOrderCount}",
          f"p:{ac.openPositionCount}")


def main():
    global account
    account = get_account()
    threading.Thread(target=run_price_stream, args=[tradeable_instruments, ]).start()
    threading.Thread(target=run_transaction_stream).start()
    threading.Thread(target=run_account_update, args=[account, lastTransactionID]).start()


if __name__ == '__main__':
    main()
