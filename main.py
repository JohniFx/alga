#!/usr/bin/python3

from typing import Any
from trader import Trader
import threading
import time
from datetime import datetime
from stats import Stat
from configparser import ConfigParser
import v20
from poll_account import AccountPolling
from stream_transaction import TransactionStream
from stream_price import PriceStream
import json

class Main():
    _threads = []

    def __init__(self) -> None:
        super().__init__()
        self.ctx = self.get_context()
        self.stats = Stat()
        self.params = self.load_params()
        self.instruments = self.get_instruments()

    def load_params(self):
        with open('params.json') as json_file:
            p = json.load(json_file)
        return p

    def save_all_instruments(self):
        insts = {i.name : i.dict() for i in self.ctx.account.instruments(self.account_id).get('instruments')}
        with open('instruments.json', 'w') as outfile:
            json.dump(insts, outfile, indent=4)

    def load_all_instruments(self):
        with open('instruments.json') as json_file:
            insts = json.load(json_file)
        return insts

    def start_threads(self):
        # Price Stream
        pEvents = {}
        self.prices = {}
        for i in self.instruments.keys():
            self.prices[i] = {}
        pLock = threading.Lock()
        ps = PriceStream(pEvents,pLock, "PriceStream", self.prices)
        ps.daemon = True
        self._threads.append(ps)

        # Transaction
        tEvents = threading.Event()
        tLock = threading.Lock()
        tr = TransactionStream(tEvents, tLock, "Transaction")
        tr.daemon = True
        self._threads.append(tr)

        # Account
        self.account = self.ctx.account.get(self.account_id).get('account')
        aEvent = threading.Event()
        aLock = threading.Lock()
        self.ap = AccountPolling(self.account, aEvent, aLock, "Account", self.ctx)
        #ap.daemon = True
        #self._threads.append(ap)

        # start threads
        for t in self._threads:
            t.start()

    def start_trading(self, n:int=120, iters:int=100):
        for i in range(iters):
            print(f'\nITER: {i} of {iters}')
            self.ap.get_account_changes()
            t = Trader(self.ctx, self.account, self.instruments, self.prices)      
            t.start()
            t.join()
            self.stats.show()
            h = datetime.now().hour
            n = 300 if h >= 22 or h <= 8 else 120
            time.sleep(n)

    def get_context(self):
        config = ConfigParser()
        config.read('config.ini')
        API_KEY = config['OANDA']['API_KEY']
        HOSTNAME = "api-fxpractice.oanda.com"
        self.account_id = config['OANDA']['ACCOUNT_ID'] # ez külön kellene
        key = f'Bearer {API_KEY}'
        ctx = v20.Context(hostname=HOSTNAME, token=key)
        ctx.set_header(key='Authorization', value=key)
        return ctx   

    def get_instruments(self):
        resp = self.ctx.account.instruments(
            self.account_id, 
            instruments=self.params['tradeable_instruments'])
        insts = resp.get('instruments')
        return {i.name: i.dict() for i in insts}

    def on_data(self, data: Any):
        excluded = ['DAILY_FINANCING',
                    'STOP_LOSS_ORDER_REJECT',
                    'MARKET_ORDER_REJECT',
                    'ORDER_CANCEL',
                    'MARKET_ORDER']
        if data.type in excluded or data.reason == 'ON_FILL':
            # print(data)
            return

        self.close_similar_trade(data)
        self.stats.update(data)

        msg = f"{datetime.now().strftime('%H:%M:%S')}"
        inst = ''
        if hasattr(data, 'instrument'):
            inst = data.instrument
        msg += f" {inst} {data.type}.{data.reason} "

        reasons_detailed = [
            'TRAILING_STOP_LOSS_ORDER',
            'TAKE_PROFIT_ORDER',
            'STOP_LOSS_ORDER',
            'MARKET_ORDER_TRADE_CLOSE',
            'MARKET_ORDER_POSITION_CLOSEOUT']

        if data.reason in reasons_detailed:
            msg += f" {data.units:.0f} PL:{data.pl}"
        print(msg)

    def close_similar_trade(self, data:Any):
        # TODO: 
        if data.type != 'ORDER_FILL':
            return
        reas = ['STOP_LOSS_ORDER', 'TRAILING_STOP_LOSS_ORDER']
        if data.reason not in reas:
            return
        if data.pl > 0:
            return

        # single trade
        for t in self.account.trades:
            if t.unrealizedPL > abs(data.pl):
                # TODO:  normalis loggolas kell
                self.ctx.trade.close(self.account_id, t.id, units='ALL')
                return

        # multiple trades
        sum_unrealized = 0
        trade_ids = []
        trades = []
        for t in self.account.trades:
            if t.unrealizedPL > 0:
                trade_ids.append(t.id)
                trades.append(t)
                sum_unrealized += t.unrealizedPL
                if sum_unrealized > abs(data.pl):
                    for trada in trades:
                        self.ctx.trade.close(self.account_id, trada.id, units='ALL')
                    return
        print('NO replacement winning trade(s)')

    def restart(self):
        import os
        import sys
        print(f'\n{u.get_now()} RESTART\n')
        os.execv('./main.py', sys.argv)
    
    def get_position_count(self) -> int:
        c = 0
        for p in self.account.positions:
            if p.marginUsed is not None:
                c+=1
        return c    
    
    def print_account(self):
        ac = self.account
        print(f" ",
              f"BAL: {float(ac.balance):7.2f}",
              f"NAV: {float(ac.NAV):>7.2f}",
              f"pl:{float(ac.unrealizedPL):>6.2f}",
              f"t:{len(ac.trades)}",
              f"p:{self.get_position_count()}")

if __name__ == '__main__':
    m = Main()
    m.start_threads()
    m.start_trading()
    m.print_account()


    try:
        for t in m._threads:
            t.join()
    except KeyboardInterrupt as error:
        print('Keyabord interrupt!')
