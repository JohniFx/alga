import v20
import threading
import configparser
import time
#
'''

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


def get_account():
    response = ctx.account.get(ACCOUNT_ID)
    return response.get('account'), response.get('lastTransactionID')


def run_account_update(account, lastTransactionID):
    print('start account polling')
    _lastId = lastTransactionID
    while True:
        try:
            account, _lastId = get_account()
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


def apply_changes(account: v20.account.Account, changes: v20.account.AccountChanges):
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
    account, lastTransactionID = get_account()
    threading.Thread(target=run_account_update, args=[account, lastTransactionID]).start()


if __name__ == '__main__':
    main()
'''
print('commented out file')