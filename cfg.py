import v20
import threading
import time
import configparser
import json
from datetime import datetime
import utils as u


class Cfg(object):
    threads = []
    ti=[]

    def __init__(self):
        #
        config = configparser.ConfigParser()
        config.read('config.ini')
        #
        API_KEY = config['OANDA']['API_KEY']
        self.ACCOUNT_ID = config['OANDA']['ACCOUNT_ID']
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
        self.threads.append(threading.Thread(target=self.run_transaction_stream))
        self.threads.append(threading.Thread(target=self.run_account_update))
        for t in self.threads:
            t.start()
        #
        _insts_csv = ','.join(self.get_tradeable_instruments()[:20])
        _insts = self.ctx.account.instruments(self.ACCOUNT_ID, instruments=_insts_csv).get('instruments')
        self.instruments = {i.name: i.dict() for i in _insts}

    def restart(self):
        import os
        import sys
        print(f'\n{u.get_now()} RESTART\n')
        os.execv('./main.py', sys.argv)

    def get_account(self):
        response = self.ctx.account.get(self.ACCOUNT_ID)
        return response.get('account')

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
            tp=55,
            sl=12,
            ts=12,
            max_spread=3,
            be_trigger=10,
            be_level=3)
        return global_params

    def notify_transaction_observers(self, data):
        for o in self.transaction_observers:
            o.on_data(data)

    def notify_account_observers(self):
        for o in self.account_observers:
            o.on_account_changes()

    def run_transaction_stream(self):
        print('start transaction stream')
        response = self.ctxs.transaction.stream(self.ACCOUNT_ID)
        try:
            for t, d in response.parts():
                if d.type != "HEARTBEAT":
                    self.notify_transaction_observers(d)
        except Exception as e:
            print('Transaction stream crashed. RESTART stream only!', e, d)
            time.sleep(5)
            self.run_transaction_stream()

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
                # self.notify_account_observers()
            except Exception as e:
                print('Account update loop crashed', e)
                time.sleep(60)
                self.restart()
            time.sleep(15)








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

    def get_positions(self) -> list:
        for p in self.account.positions:
            if p.marginUsed is not None:
                yield p

    def get_position_by_instrument(self, inst)->v20.position.Position:
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
