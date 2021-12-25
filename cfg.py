import v20
from v20.account import AccountChanges
import threading
import time
import configparser

config = configparser.ConfigParser()
config.read('config.ini')

API_KEY = config['OANDA']['API_KEY'] 
ACCOUNT_ID = config['OANDA']['ACCOUNT_ID']
HOSTNAME   = "api-fxpractice.oanda.com"
STREAMHOST = "stream-fxpractice.oanda.com"
key = f'Bearer {API_KEY}'

# contexts
ctx = v20.Context(hostname=HOSTNAME, token=key)
ctx.set_header(key='Authorization', value=key)
ctxs = v20.Context(hostname=STREAMHOST, token=key)
ctxs.set_header(key='Authorization', value=key)

# global account_id 
def get_account():
    response = ctx.account.get(ACCOUNT_ID)
    return response.get('account'), response.get('lastTransactionID')

account, lastTransactionID = get_account()

messages = []

insts = ctx.account.instruments(ACCOUNT_ID).get('instruments')
instruments = {i.name:i.dict() for i in insts}


price_observers = []
transaction_observers = []
account_observers = []

global_params = dict(
    tp=10,
    sl=10,
    ts=11)
# print(global_params)

def notify_price_observers(cp):
    for o in price_observers:
        o.on_tick(cp)

def notify_transaction_observers(data):
    for o in transaction_observers:
        o.on_data(data)

def notify_account_observers():
    for o in account_observers:
        o.on_account_changes()

def run_price_stream():
    print('running price stream')
    response = ctxs.pricing.stream(ACCOUNT_ID, instruments='EUR_AUD,EUR_USD')
    for typ, data in response.parts():
        if typ == "pricing.ClientPrice":
            cp = dict(
                i=data.instrument,
                bid=data.bids[0].price,
                ask=data.asks[0].price)
            notify_price_observers(cp)
            instruments[data.instrument]['bid']=data.bids[0].price
            instruments[data.instrument]['ask']=data.asks[0].price
            instruments[data.instrument]['spread']=round(data.asks[0].price-data.bids[0].price, instruments[data.instrument]['displayPrecision'])


def run_transaction_stream():
    print('running transaction stream')
    response = ctxs.transaction.stream(ACCOUNT_ID)
    for t, d in response.parts():
        if d.type != "HEARTBEAT":
            notify_transaction_observers(d)

def run_account_update(account, lastTransactionID):
    print('running account update polling')
    _lastId = lastTransactionID

    while True:
        r = ctx.account.changes(
            ACCOUNT_ID,
            sinceTransactionID=_lastId)
        changes = r.get('changes')
        state = r.get('state')
        _lastId = r.get('lastTransactionID')
        update_account(account, changes, state)
        notify_account_observers()
        time.sleep(15)

def update_trades(account, state):
    for tc in state.trades:
        for t in account.trades:
            if t.id == tc.id:
                t.unrealizedPL = tc.unrealizedPL
                t.marginUsed = tc.marginUsed

def update_fields(account, state):
    for field in state.fields():
        update_attribute(account, field.name, field.value)

def update_positions(account, state):
    for po in state.positions:
        for p in account.positions:
            if p.instrument == po.instrument:
                p.netUnrealizedPL = po.netUnrealizedPL
                p.longUnrealizedPL = po.longUnrealizedPL
                p.shortUnrealizedPL = po.shortUnrealizedPL
                p.marginUsed = po.marginUsed
                # update short.tradeIDs, units, averagePrice

def update_orders(account, state):
    for so in state.orders:
        for o in account.orders:
            if o.id == so.id:
                o.trailingStopValue = so.trailingStopValue
                o.distance = so.triggerDistance


def apply_changes(account, changes: AccountChanges):
    for to in changes.tradesOpened:
        account.trades.append(to)
        #new_trade_count += 1

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

    for p in changes.positions:
        for ap in account.positions:
            if p.instrument == ap.instrument:
                account.positions.remove(ap)
                account.positions.append(p)

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


def update_attribute(dest, name, value):
    if name in ('orders', 'trades', 'positions'):
        return
    if hasattr(dest, name) and getattr(dest, name) is not None:
        setattr(dest, name, value)

def update_account(account, changes, state):
  #  print('applying changes on account',f'{account.NAV}')
    apply_changes(account, changes)
    update_fields(account, state)
    update_trades(account, state)
    update_positions(account, state)
    update_orders(account, state)

   
def check_breakeven_for_position(trades, instrument):
    all_breakeven = []
    for t in trades:
        if t.instrument == instrument:
            all_breakeven.append(
                (t.currentUnits > 0 and t.stopLossOrder.price >= t.price)
                or
                (t.currentUnits < 0 and t.stopLossOrder.price <= t.price))
    return all(all_breakeven)


def get_trades_by_instrument(trades, instrument):
    inst_trades = []
    for t in trades:
        if t.instrument == instrument:
            inst_trades.append(t)
    return inst_trades

threading.Thread(target=run_price_stream).start()
threading.Thread(target=run_transaction_stream).start()
threading.Thread(target=run_account_update, args=[account, lastTransactionID]).start()

