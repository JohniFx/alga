#!/usr/bin/python3

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
        threading.Thread(target=self.restart).start()
        cfg.price_observers.append(self)
        cfg.transaction_observers.append(self)
        cfg.account_observers.append(self)
        time.sleep(5)

        self.stats = cfg.create_stats()

        threading.Thread(target=self.update_kpi).start()
        threading.Thread(target=Main.run_check_instruments).start()

    def update_kpi(self):
        while True:
            q = quant.Quant()
            q.fetch_data()
            q.fetch_data(tf='D', count='10')
            q.update_kpi_file()
            time.sleep(60*30)

    @staticmethod
    def run_check_instruments(n=120):
        while True:
            t = trader.Trader()
            threading.Thread(target=t.do_trading).start()
            time.sleep(n)

    def on_tick(self, cp):
        # margin calculation
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
            msg += f" {data.units} PL:{data.pl}, cost:{data.halfSpreadCost}"
        print(msg)

    def on_account_changes(self):
        # print('on account changes')
        if datetime.now().minute % 15 == 0:
            msg = f"{datetime.now().strftime('%H:%M:%S')}"
            msg += f" {float(cfg.account.NAV):>7.2f}"
            msg += f" {float(cfg.account.unrealizedPL):>7.2f}"
            msg += f" t:{cfg.account.openTradeCount}"
            msg += f" o:{cfg.account.pendingOrderCount}"
            msg += f" p:{cfg.account.openPositionCount}"
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
        else:
            return
        pp.pprint(self.stats)
        with open('stats.json', w) as f:
            json.dump(self.stats, f, indent=2)

    def restart(self):
        time.sleep(30*60)
        import os
        import sys
        print(f'\n{u.get_now()} ')
        os.execv('./main.py', sys.argv)


if __name__ == '__main__':
    try:
        m = Main()
    except KeyboardInterrupt:
        print('close threads gracefully')
