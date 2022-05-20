import v20
import threading
import time
import configparser
import json
from datetime import datetime
import utils as u


class Cfg(object):
    threads = []

    def __init__(self):
        #
        config = configparser.ConfigParser()
        config.read('config.ini')
        #
        API_KEY = config['OANDA2']['API_KEY']
        self.ACCOUNT_ID = config['OANDA2']['ACCOUNT_ID']
        HOSTNAME = "api-fxpractice.oanda.com"
        STREAMHOST = "stream-fxpractice.oanda.com"
        key = f'Bearer {API_KEY}'
        # contexts
        self.ctx = v20.Context(hostname=HOSTNAME, token=key)
        self.ctx.set_header(key='Authorization', value=key)
        self.ctxs = v20.Context(hostname=STREAMHOST, token=key)
        self.ctxs.set_header(key='Authorization', value=key)
        #
        self.price_observers = []
        self.transaction_observers = []
        self.account_observers = []
        #
        self.account = self.get_account()
        self.threads.append(threading.Thread(target=self.run_price_stream))
        self.threads.append(threading.Thread(target=self.run_transaction_stream))
        self.threads.append(threading.Thread(target=self.run_account_update))
        for t in self.threads:
            t.start()
        #
        insts = self.ctx.account.instruments(self.ACCOUNT_ID).get('instruments')
        self.instruments = {i.name: i.dict() for i in insts}

    def restart(self):
        import os
        import sys
        print(f'\n{u.get_now()} RESTART\n')
        os.execv('./main.py', sys.argv)

    def get_account(self):
        response = self.ctx.account.get(self.ACCOUNT_ID)
        return response.get('account')

    ti=[]
    def get_tradeable_instruments(self):
        if len(self.ti) == 0:
            self.ti = [
            'EUR_USD', 'EUR_CAD', 'EUR_NZD', 'EUR_CHF', 'EUR_JPY', 'EUR_AUD', 'EUR_GBP',
            'GBP_USD', 'GBP_CAD', 'GBP_JPY', 'GBP_AUD',
            'AUD_USD', 'AUD_CAD', 'AUD_NZD', 'AUD_JPY',
            'NZD_USD', 'NZD_JPY',
            'USD_CHF', 'USD_CAD', 'USD_JPY']
        return self.ti

    def set_tradeable_instruments(self, inst:str):
        self.ti.remove(inst)

    def get_global_params(self):
        global_params = dict(
            tp=35,
            sl=12,
            ts=15,
            max_spread=3,
            be_pips=12,
            be_sl=3)
        return global_params

    def notify_price_observers(self, cp):
        for o in self.price_observers:
            o.on_tick(cp)

    def notify_transaction_observers(self, data):
        for o in self.transaction_observers:
            o.on_data(data)

    def notify_account_observers(self):
        for o in self.account_observers:
            o.on_account_changes()

    def run_price_stream(self):
        print('start price stream')
        tradeinsts = ','.join(self.get_tradeable_instruments()[:20])
        response = self.ctxs.pricing.stream(self.ACCOUNT_ID, instruments=tradeinsts)
        try:
            for typ, data in response.parts():
                if typ == "pricing.ClientPrice":
                    cp = dict(
                        i=data.instrument,
                        bid=data.bids[0].price,
                        ask=data.asks[0].price)
                    self.notify_price_observers(cp)
                    self.instruments[data.instrument]['bid'] = data.bids[0].price
                    self.instruments[data.instrument]['ask'] = data.asks[0].price
                    self.instruments[data.instrument]['spread'] = round(
                        data.asks[0].price-data.bids[0].price,
                        self.instruments[data.instrument]['displayPrecision'])
        except ValueError as e:
            print('ValueError in pricestream', e)
        except Exception as e:
            print('Exception in price stream, RESTART', e)
            time.sleep(5)
            self.restart()

    def run_transaction_stream(self):
        print('start transaction stream')
        response = self.ctxs.transaction.stream(self.ACCOUNT_ID)
        # try:
        for t, d in response.parts():
            if d.type != "HEARTBEAT":
                self.notify_transaction_observers(d)
        # except Exception as e:
            # print('Transaction stream crashed. RESTART', e, d)
            # time.sleep(5)
            # self.restart()

    def run_account_update(self):
        print('start account polling')
        _lastId = self.account.lastTransactionID

        while True:
            try:
                r = self.ctx.account.changes(self.ACCOUNT_ID,
                                             sinceTransactionID=_lastId)
                changes = r.get('changes')
                state = r.get('state')
                _lastId = r.get('lastTransactionID')
                self.update_account(changes, state)
                self.notify_account_observers()
            except Exception as e:
                print('Account update loop crashed', e)
                time.sleep(60)
                self.restart()
            time.sleep(15)

    def update_account(self,
                       changes: v20.account.AccountChanges,
                       state: v20.account.AccountChangesState):
        self.apply_changes(changes)
        self.apply_transactions(changes)
        #
        self.update_fields(state)
        self.update_trades(state)
        self.update_positions(state)
        self.update_orders(state)

    def apply_transactions(self, changes):
        for tr in changes.transactions:
            if tr.type == 'ORDER_FILL':
                self.account.balance = tr.accountBalance

    def update_trades(self, state):
        for st in state.trades:
            for at in self.account.trades:
                if at.id == st.id:
                    at.unrealizedPL = st.unrealizedPL
                    at.marginUsed = st.marginUsed

    def update_fields(self, state):
        for field in state.fields():
            self.update_attribute(self.account, field.name, field.value)

    def update_attribute(self, dest, name, value):
        if name in ('orders', 'trades', 'positions'):
            return
        if hasattr(dest, name) and getattr(dest, name) is not None:
            setattr(dest, name, value)

    def update_positions(self, state: v20.account.AccountChangesState):
        for sp in state.positions:
            for p in self.account.positions:
                if p.instrument == sp.instrument:
                    p.unrealizedPL = sp.netUnrealizedPL
                    p.long.unrealizedPL = sp.longUnrealizedPL
                    p.short.unrealizedPL = sp.shortUnrealizedPL
                    p.marginUsed = sp.marginUsed

    def update_orders(self, state):
        for so in state.orders:
            for o in self.account.orders:
                if o.id == so.id:
                    o.trailingStopValue = so.trailingStopValue
                    o.distance = so.triggerDistance

    def apply_changes(self, changes: v20.account.AccountChanges):
        # Trades Opened
        for to in changes.tradesOpened:
            self.account.trades.append(to)
        # Trades Reduced
        for tr in changes.tradesReduced:
            for t in self.account.trades:
                if t.id == tr.id:
                    t.currentUnits = tr.currentUnits
                    t.realizedPL = tr.realizedPL
                    t.averageClosePrice = tr.averageClosePrice
        # Trades Closed
        for tc in changes.tradesClosed:
            for t in self.account.trades:
                if t.id == tc.id:
                    self.account.trades.remove(t)
        #
        for cp in changes.positions:
            for ap in self.account.positions:
                if ap.instrument == cp.instrument:
                    self.account.positions.remove(ap)
                    self.account.positions.append(cp)
        #
        for occ in changes.ordersCancelled:
            for o in self.account.orders:
                if o.id == occ.id:
                    self.account.orders.remove(o)
                    for t in self.account.trades:
                        if t.id == occ.tradeID:
                            if occ.type == 'STOP_LOSS':
                                t.stopLossOrderID = None
                            elif occ.type == 'TAKE_PROFIT':
                                t.takeProfitOrderID = None
                            elif occ.type == 'TRAILING_STOP_LOSS':
                                t.trailingStopLossOrderID = None
        #
        for ocr in changes.ordersCreated:
            self.account.orders.append(ocr)
            for t in self.account.trades:
                # AttributeError: 'StopOrder' object has no attribute 'tradeID'
                if t.id == ocr.tradeID:
                    if ocr.type == 'STOP_LOSS':
                        t.stopLossOrderID = ocr.id
                    elif ocr.type == 'TAKE_PROFIT':
                        t.takeProfitOrderID = ocr.id
                    elif ocr.type == 'TRAILING_STOP_LOSS':
                        t.trailingStopLossOrderID = ocr.id
        #
        for ofi in changes.ordersFilled:
            for o in self.account.orders:
                if o.id == ofi.id:
                    self.account.orders.remove(o)
        #
        for otr in changes.ordersTriggered:
            for o in self.account.orders:
                if o.id == otr.id:
                    self.account.orders.remove(o)

    def print_account(self):
        ac = self.account
        print(f"{u.get_now()}",
              f"BAL: {float(ac.balance):7.2f}",
              f"NAV: {float(ac.NAV):>7.2f}",
              f"pl:{float(ac.unrealizedPL):>6.2f}",
              f"t:{len(ac.trades)}",
              f"p:{self.get_position_count()}")

    def get_position_count(self) -> int:
        c = 0
        for p in self.account.positions:
            if p.marginUsed is not None:
                c+=1
        return c

    def get_positions(self):
        for p in self.account.positions:
            if p.marginUsed is not None:
                yield p

    def get_position_by_instrument(self, inst)->list:
        for p in self.account.positions:
            if p.marginUsed is not None:
                if p.instrument == inst:
                    return p
        return None

    def get_trades_by_instrument(self, inst) ->list:
        for t in self.account.trades:
            if t.instrument == inst:
                yield t

    def get_trade_by_id(self, tradeid: int) -> v20.trade.TradeSummary:
        for t in self.account.trades:
            if t.id == tradeid:
                return t

    def get_order_by_id(self, orderid: int) -> v20.order.Order:
        for o in self.account.orders:
            if o.id == orderid:
                return o

    def get_piploc(self, inst):
        #
        return self.instruments[inst]['pipLocation']


if __name__ == '__main__':
    c = Cfg()
