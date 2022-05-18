#!/usr/bin/python3
from cfg import Cfg
import trader
import quant
import threading
import time
from datetime import datetime
import utils as u
import json
__version__ = '2022-05-17'


class Main(Cfg):
    def __init__(self) -> None:
        super().__init__()

        self.price_observers.append(self)
        self.transaction_observers.append(self)
        self.account_observers.append(self)
        time.sleep(5)
        self.stats = self.create_stats()
        self.print_account()
        threading.Thread(target=self.update_kpi).start()
        threading.Thread(target=self.run_check_instruments).start()

    def update_kpi(self):
        while True:
            q = quant.Quant(self)
            q.fetch_data()
            q.fetch_data(tf='D', count='10')
            q.update_kpi_file()
            time.sleep(60*30)

    def run_check_instruments(self, n=120):
        iters = 30
        for i in range(iters):
            print(f'\n{u.get_now()} ITER: {i} of {iters}')
            t = trader.Trader(self)
            threading.Thread(target=t.do_trading).start()
            hour = datetime.now().hour
            n = 300 if hour >= 22 or hour <= 8 else 120
            time.sleep(n)
        self.restart()

    def on_tick(self, cp):
        pass

    def on_data(self, data):
        self.update_stats(data)
        if data.type == 'DAILY_FINANCING':
            print(data)
            return

        if data.type == 'STOP_LOSS_ORDER_REJECT':
            print(data)

        if data.type == 'MARKET_ORDER_REJECT':
            print(data.type, data.tradeClose.tradeID)

        if data.type == 'ORDER_FILL' and data.reason == 'STOP_LOSS_ORDER':
            if data.pl < 0:
                self.close_similar_trade(abs(data.pl))
        if data.type == 'ORDER_FILL' and data.reason == 'TRAILING_STOP_LOSS_ORDER':
            if data.pl < 0:
                self.close_similar_trade(abs(data.pl))

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
            msg += f" {data.units:.0f} PL:{data.pl}"
        print(msg)

    def close_similar_trade(self, pl_value):
        for t in self.account.trades:
            # single trade
            if t.unrealizedPL > pl_value:
                self.ctx.trade.close(self.ACCOUNT_ID, t.id, units='ALL')
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
                if sum_unrealized > pl_value:
                    for trada in trades:
                        self.trade.close(self.ACCOUNT_ID, trada.id, units='ALL')
                    return

        print('NO replacement winning trade(s)')

    def on_account_changes(self):
        pass

    def update_stats(self, data):
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
        self.print_stats(self.stats)
        with open('stats.json', 'w') as f:
            json.dump(self.stats, f, indent=2)


if __name__ == '__main__':
    m = Main()
