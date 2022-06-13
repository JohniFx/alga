#!/usr/bin/python3
from cfg import Cfg
from price_stream import PriceProcessor, PriceStream, WorkProcessor
import trader
import quant
import threading
from queue import Queue
import time
from datetime import datetime
import utils as u
from stats import Stat
__version__ = '2022-05-17'

class Main(Cfg):
    watchlist = []

    def __init__(self) -> None:
        super().__init__()
        self.stats = Stat()
        #observers
        self.transaction_observers.append(self)
        self.account_observers.append(self)
        time.sleep(4)
        # threads
        # price stream
        # account polling
        # transaction stream
        # trading 
        self.t = trader.Trader(self)
        self.print_account()
        t1 = threading.Thread(target=self.update_kpi)
        t1.start()

        t2 = threading.Thread(target=self.run_trading)
        t2.start()

    def update_kpi(self):
        while True:
            q = quant.Quant(self)
            q.fetch_data()
            q.fetch_data(tf='D', count='10')
            q.update_kpi_file()
            time.sleep(60*30)

    def run_trading(self, n=120, iters=5):
        for i in range(iters):
            print(f'\n{u.get_now()} ITER: {i} of {iters}')
            self.t.manage_trading()
            # threading.Thread(target=t.do_trading).start()
            # threading.Thread(target=t.manage_trading).start()
            self.stats.show()
            self.print_account()
            h = datetime.now().hour
            n = 300 if h >= 22 or h <= 8 else 120
            time.sleep(n)
        self.restart()

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


if __name__ == '__main__':
    threads = []

    events = {}
    shared_prices = {}
    lock = threading.Lock()
    work_queue = Queue()

    insts = ['EUR_USD', 'GBP_USD', 'USD_JPY', 'AUD_USD', 'AUD_JPY']
    for i in insts:
        events[i] = threading.Event()
        shared_prices[i] = {}
    
    # create pricestream
    ps = PriceStream(events, shared_prices, lock, f"PriceStream_LOG")
    ps.daemon = True
    threads.append(ps)
    ps.start()

    wp = WorkProcessor(work_queue)
    wp.daemon = True
    threads.append(wp)
    wp.start()

    for i in insts:
        t = PriceProcessor(events, shared_prices, lock, f"PriceProcessor_{i}_LOG",
            i,
            work_queue)
        t.daemon = True
        threads.append(t)
        t.start()
    
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt as error:
        print('keyboard:', error)
    m = Main()
