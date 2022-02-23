#!/usr/bin/env python

import cfg
import trader
import quant
import threading
import time
from datetime import datetime
__version__ = '2022-02-06'

class Main():
    def __init__(self) -> None:
        self.t = trader.Trader()
        cfg.price_observers.append(self)
        cfg.transaction_observers.append(self)
        cfg.account_observers.append(self)

        threading.Thread(target=self.update_kpi).start()
        time.sleep(5)
        self.initial_tradecheck()
        #TODO: ide kell egy általános ellenőrző metodus; minden poziciót ellenőriz, stopot berak ha nincs, breakeven-be huz ha nem lenne
        threading.Thread(target=self.run_check_instruments).start()

    def update_kpi(self):
        while True:
            # print('updating kpi')
            q = quant.Quant()
            q.fetch_data()
            q.fetch_data(tf='D', count='10')
            q.update_kpi_file()
            time.sleep(60*30)

    def run_check_instruments(self):
        while True:           
            self.t.check_instruments(cfg.tradeable_instruments)
            time.sleep(120)

    def on_tick(self, cp):
        pass
        # if 'spread' not in cfg.instruments[cp['i']]:
        #     msg = f"{datetime.now().strftime('%H:%M:%S')}"
        #     msg += f" {cp['i']}: {cp['bid']:.5f} / {cp['ask']:.5f}"
        #     print(msg, 'no spread')

    def on_data(self, data):
        msg = f"{datetime.now().strftime('%H:%M:%S')}"
        inst = ''
        if hasattr(data, 'instrument'):
            inst = data.instrument
        types = [
            'ORDER_CANCEL',
            'MARKET_ORDER'
        ]
        reasons = [
            # 'REPLACEMENT', 
            # 'CLIENT_REQUEST_REPLACED', 
            'ON_FILL',
            # 'LINKED_TRADE_CLOSED',
            # 'CLIENT_ORDER'
            ]
        if (data.type in types) or (data.reason in reasons):
            return
        msg += f" {data.id} {data.type}.{data.reason} {inst}"
        if data.reason in ['TRAILING_STOP_LOSS_ORDER','TAKE_PROFIT_ORDER', 'STOP_LOSS_ORDER']:
            print('show closed positions pl')
            msg += f" {data.units} PL:{data.pl}, cost:{data.halfSpreadCost}"

        
        print(msg)

    def on_account_changes(self):
        # print('on account changes')
        if datetime.now().minute%15==0:
            msg = f"{datetime.now().strftime('%H:%M:%S')}"
            msg+= f" {float(cfg.account.NAV):>7.2f}"
            msg+= f" {float(cfg.account.unrealizedPL):>8.4f}"
            msg+= f" t:{len(cfg.account.trades)}"
            msg+= f" o:{len(cfg.account.orders)}"
            msg+= f" p:{self.get_open_positions()}"
            print(msg)

    def get_open_positions(self):
        openpos = []
        for p in cfg.account.positions:
            if p.marginUsed is not None:
                openpos.append(p)
        return len(openpos)

    def show_prices(self):
        r = cfg.ctx.pricing.get(cfg.ACCOUNT_ID, instruments='EUR_USD')
        prices = r.get('prices')
        for p in prices:
            print(p)

    def initial_tradecheck(self):
        for t in cfg.account.trades:
            if t.stopLossOrderID is None:
                if t.unrealizedPL >= 0:
                    self.t.add_stop(t)
                else:
                    print('Close trade without stop')
                    self.t.close_trade(t)



if __name__ == '__main__':
    try:
        m = Main()
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
