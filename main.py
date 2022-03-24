#!/usr/bin/python3
import os
import sys

import cfg
import trader
import quant
import threading
import time
from datetime import datetime
import pprint
import utils as u
import json
__version__ = '2022-03-16'


class Main():
    def __init__(self) -> None:
        cfg.price_observers.append(self)
        cfg.transaction_observers.append(self)
        cfg.account_observers.append(self)
        self.stats = cfg.create_stats()
        time.sleep(5)
        threading.Thread(target=self.update_kpi).start()
        threading.Thread(target=self.run_check_instruments).start()

    def update_kpi(self):
        while True:
            q = quant.Quant()
            q.fetch_data()
            q.fetch_data(tf='D', count='10')
            q.update_kpi_file()
            time.sleep(60*30)

    def run_check_instruments(self, n=120):
        for i in range(15):
            print(f'\n{u.get_now()} ITER: {i}')
            t = trader.Trader()
            threading.Thread(target=t.do_trading).start()
            hour = datetime.now().hour
            n = 300 if hour >= 22 or hour <= 7 else 120
            time.sleep(n)
        self.restart()

    def restart(self):
        print(f'\n{u.get_now()} RESTART')
        os.execv('./main.py', sys.argv)

    def on_tick(self, cp):
        pass

    def on_data(self, data):
        self.update_stats(data)

        if data.type == 'STOP_LOSS_ORDER_REJECT':
            print(data)

        if data.type == 'MARKET_ORDER_REJECT':
            print(data)

        types = ['ORDER_CANCEL', 'MARKET_ORDER']
        reasons = ['ON_FILL']
        if (data.type in types) or (data.reason in reasons):
            return

        msg = f"{datetime.now().strftime('%H:%M:%S')}"
        inst = ''
        if hasattr(data, 'instrument'):
            inst = data.instrument
        msg += f" {data.id} {data.type}.{data.reason} {inst}"

        reasons_detailed = [
            'TRAILING_STOP_LOSS_ORDER',
            'TAKE_PROFIT_ORDER',
            'STOP_LOSS_ORDER',
            'MARKET_ORDER_TRADE_CLOSE',
            'MARKET_ORDER_POSITION_CLOSEOUT']

        if data.reason in reasons_detailed:
            msg += f" {data.units:.0f} PL:{data.pl}, cost:{data.halfSpreadCost}"
        print(msg)

    def on_account_changes(self):
        if datetime.now().minute % 5 == 0:
            self.print_account(cfg.account)

    def print_account(self, ac):
        if datetime.now().minute % 15 == 0:
            msg = f"{datetime.now().strftime('%H:%M:%S')}"
            msg += f" nav:{float(ac.NAV):>7.2f}"
            msg += f" pl:{float(ac.unrealizedPL):>6.2f}"
            msg += f" t:{ac.openTradeCount}"
            msg += f" o:{ac.pendingOrderCount}"
            msg += f" p:{ac.openPositionCount}"
            print(msg)

    def update_stats(self, data):
        pp = pprint.PrettyPrinter(indent=4)
        if data.reason == 'TAKE_PROFIT_ORDER':
            self.stats['count_tp'] += 1
            self.stats['sum_tp'] += data.pl
        elif data.reason == 'STOP_LOSS_ORDER':
            self.stats['count_sl'] += 1
            self.stats['sum_sl'] += data.pl
        elif data.reason == 'TRAILING_STOP_LOSS_ORDER':
            self.stats['count_ts'] += 1
            self.stats['sum_ts'] += data.pl
        elif data.reason == 'MARKET_ORDER_TRADE_CLOSE':
            self.stats['count_manual'] += 1
            self.stats['sum_manual'] += data.pl
        else:
            return
        pp.pprint(self.stats)
        with open('stats.json', 'w') as f:
            json.dump(self.stats, f, indent=2)


if __name__ == '__main__':
    try:
        m = Main()
    except KeyboardInterrupt:
        print('close threads gracefully')
