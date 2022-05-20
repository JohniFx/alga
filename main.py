#!/usr/bin/python3
from cfg import Cfg
import trader
import quant
import threading
import time
from datetime import datetime
import utils as u
from stats import Stat
__version__ = '2022-05-17'


class Main(Cfg):
    def __init__(self) -> None:
        super().__init__()
        self.stats = Stat()
        self.price_observers.append(self)
        self.transaction_observers.append(self)
        self.account_observers.append(self)
        time.sleep(4)

        self.print_account()
        t1 = threading.Thread(target=self.update_kpi)
        t1.start()

        t2 = threading.Thread(target=self.run_check_instruments)
        t2.start()


    def update_kpi(self):
        while True:
            q = quant.Quant(self)
            q.fetch_data()
            q.fetch_data(tf='D', count='10')
            q.update_kpi_file()
            time.sleep(60*30)

    def run_check_instruments(self, n=120, iters=5):
        for i in range(iters):
            print(f'\n{u.get_now()} ITER: {i} of {iters}')
            t = trader.Trader(self)
            t3= threading.Thread(target=t.do_trading)
            threading.Thread(target=t.do_trading_simu).start()
            t3.start()
            self.stats.show()
            h = datetime.now().hour
            n = 300 if h >= 22 or h <= 8 else 120
            time.sleep(n)
        self.restart()

    def on_tick(self, cp):
        pass

    def on_data_detailed(self, data):
        pass

    def on_data(self, data):
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

    def close_similar_trade(self, data):
        if data.type != 'ORDER_FILL':
            return
        reas = ['STOP_LOSS_ORDER', 'TRAILING_STOP_LOSS_ORDER']
        if data.reason not in reas:
            return
        if data.pl > 0:
            return
        for t in self.account.trades:
            # single trade
            if t.unrealizedPL > abs(data.pl):
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
                if sum_unrealized > abs(data.pl):
                    for trada in trades:
                        self.ctx.trade.close(self.ACCOUNT_ID, trada.id, units='ALL')
                    return

        print('NO replacement winning trade(s)')

    def on_account_changes(self):
        pass

if __name__ == '__main__':
    m = Main()
