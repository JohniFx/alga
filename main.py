#!/usr/bin/env python

import cfg
import trader
import quant
import threading
import time
from datetime import datetime


class Main():
    def __init__(self) -> None:
        cfg.price_observers.append(self)
        cfg.transaction_observers.append(self)
        cfg.account_observers.append(self)
        threading.Thread(target=self.update_kpi).start()
        time.sleep(5)
        threading.Thread(target=self.run_check_instruments).start()

    def update_kpi(self):
        while True:
            print('updating kpi')
            q = quant.Quant()
            q.fetch_data()
            q.fetch_data(tf='D', count='10')
            q.update_kpi_file()
            time.sleep(60*30)


    def run_check_instruments(self):
        print('run check instruments 120sec loop')
        while True:            
            self.t = trader.Trader()
            self.t.check_instruments()
            time.sleep(120)

    def on_tick(self, cp):
        if 'spread' not in cfg.instruments[cp['i']]:
            msg = f"{datetime.now().strftime('%H:%M:%S')}"
            msg += f" {cp['i']}: {cp['bid']:.5f} / {cp['ask']:.5f}"
            print(msg, 'no spread')

    def on_data(self, data):
        msg = f"{datetime.now().strftime('%H:%M:%S')}"
        inst = ''
        if hasattr(data, 'instrument'):
            inst = data.instrument
        texts = ['REPLACEMENT', 'CLIENT_REQUEST_REPLACED']
        if data.reason not in texts:
            msg += f" {data.id} {data.type} {data.reason} {inst}"
            print(msg)

    def on_account_changes(self):
        msg = f"{datetime.now().strftime('%H:%M:%S')}"
        msg+= f" {cfg.account.NAV}"
        msg+= f" {cfg.account.unrealizedPL}"
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


if __name__ == '__main__':
    m = Main()
