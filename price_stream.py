from ast import Try
from asyncio.log import logger
from queue import Queue
import random
import threading
import configparser
import requests
import json
from dateutil import parser
import copy
import time
from log_wrapper import LogWrapper
instruments = ['EUR_USD', 'EUR_AUD', 'GBP_USD', 'EUR_JPY', 'EUR_CAD', 'EUR_GBP']

class LivePrice():
    def __init__(self, ob):
        self.instrument = ob['instrument']
        self.ask = float(ob['asks'][0]['price'])
        self.bid = float(ob['bids'][0]['price'])
        self.time= parser.parse(ob['time'])

    def get_dict(self):
        return dict(
            instrument=self.instrument,
            ask=self.ask,
            bid=self.bid,
            time=self.time
        )

    def __repr__(self):
        return f"LivePrice: {self.instrument} {self.ask} {self.bid} {self.time}"

class StreamBase(threading.Thread):
    def __init__(self, events, prices, lock, logname) -> None:
        super().__init__()
        self.events = events
        self.prices = prices
        self.lock = lock
        self.log = LogWrapper(logname)
    
    def log_message(self, msg, error=False):
        if error == True:
            self.log.logger.error(msg)
        else:            
            self.log.logger.debug(msg)

class PriceStream(StreamBase):
    def __init__(self, events, prices, lock: threading.Lock, logname) -> None:
        super().__init__(events, prices, lock, logname)
        config = configparser.ConfigParser()
        config.read('config.ini')
        self.ACCOUNT_ID = config['OANDA2']['ACCOUNT_ID']
        self.SECURE_HEADER = {
            "Authorization": f"Bearer {config['OANDA2']['API_KEY']}",
            "Content-Type": "application/json"}
        self.insts = prices.keys()
        print(self.insts, self.ACCOUNT_ID, self.SECURE_HEADER)
        self.log = LogWrapper(logname)

    def update_live_price(self, live_price:LivePrice):
        try:
            self.lock.acquire()
            self.prices[live_price.instrument] = live_price
            self.set_event(live_price.instrument)
        except Exception as error:
            self.log_message(f"Exception: {error}", error=True)
        finally:
            self.lock.release()

    def set_event(self, instrument):
        if self.events[instrument].is_set() == False:
            self.events[instrument].set()

    def run(self):
        params = dict(instruments=','.join(self.insts))
        url = f"https://stream-fxpractice.oanda.com/v3/accounts/{self.ACCOUNT_ID}/pricing/stream"
        print(url, params)
        try:
            resp = requests.get(url, params=params, headers=self.SECURE_HEADER, stream=True)
            print(resp)
        except Exception as e:
            self.log_message(f'request error:', e)
        for p in resp.iter_lines():
            if p: 
                try:
                    dp = json.loads(p.decode('utf-8'))                
                    if 'type' in dp and dp['type'] == 'PRICE':
                        self.update_live_price(LivePrice(dp))
                except json.decoder.JSONDecodeError as e:
                    self.log_message(f'json.decoder {e}')

class PriceProcessor(StreamBase):
    def __init__(self, events, prices, lock, logname, inst, work_queue:Queue) -> None:
        super().__init__(events, prices, lock, logname)
        self.inst = inst
        self.work_queue = work_queue

    def process_price(self):
        price = None
        try:
            self.lock.acquire()
            price = copy.deepcopy(self.prices[self.inst])
        except Exception as error:
            self.log.logger.error(f"Exception in priceprocessor: {error}")
        finally:
            self.lock.release()

        if price is None:
            print('PRICE IS NONE, or null')
            self.log_message("No Price",True)
            return

        print(f'  thread {self.ident} processing price:', price)
        time.sleep(random.randint(2,7))
        print(f'  thread {self.ident} processing complete {price}')
        if random.randint(2,5) == 3:
            print('new work added to queue')
            price.job = 'BUY'
            self.work_queue.put(price)

    def run(self):
        while True:
            self.events[self.inst].wait()
            self.process_price()
            self.events[self.inst].clear()

class WorkProcessor(threading.Thread):
    def __init__(self, work_queue: Queue) -> None:
        super().__init__()
        self.work_queue = work_queue
        self.log = LogWrapper('WorkProcessor')

    def run(self):
        while True:
            print(f'Queue Size: {self.work_queue.qsize()}')
            item = self.work_queue.get()
            print(f'working on item: {item.job} {item.instrument}')
            # self.log.logger.debug(f'new work: {item}')
            if self.work_queue.qsize()>100:
                time.sleep(1)
            else:
                time.sleep(4)
            print(f'completed item: {item.job} {item.instrument}')

class TransactionStream(threading.Thread):
    def __init__(self,tEvents, transactions, tran_lock, logname):
        super().__init__()
    
    def run(self) -> None:
        return super().run()

if __name__ == '__main__':
    threads = []

    events = {}
    prices = {}
    lock = threading.Lock()
    work_queue = Queue()

    for i in instruments:
        events[i] = threading.Event()
        prices[i] = {}

    ps = PriceStream(events, prices, lock, "PriceStream")
    ps.daemon = True
    threads.append(ps)
    ps.start()

    wp = WorkProcessor(work_queue)
    wp.daemon = True
    threads.append(wp)
    wp.start()

    for i in instruments:
        t = PriceProcessor(events, prices, lock, f"LOG_{i}", i, work_queue)
        t.daemon = True
        threads.append(t)
        t.start()

    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print('Keyboard interrupt')
