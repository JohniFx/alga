from ast import Try
from asyncio.log import logger
from queue import Queue
import random
import threading

import requests
import json
from dateutil import parser
import copy
import time
from utils.log_wrapper import LogWrapper
instruments = ['EUR_USD', 'EUR_AUD', 'GBP_USD', 'EUR_JPY', 'EUR_CAD', 'EUR_GBP']


class StreamBase(threading.Thread):



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

        print(f'thread {self.ident} processing price:', price)
        time.sleep(random.randint(2,7))
        print(f'thread {self.ident} processing complete {price}')
        if random.randint(2,5) == 3:
            print('  new work added to queue')
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
            print(f'.  working on item: {item.job} {item.instrument}')
            self.log.logger.debug(f'new work: {item}')
            if self.work_queue.qsize()>100:
                time.sleep(1)
            else:
                time.sleep(4)
            print(f'.  completed item: {item.job} {item.instrument}')

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
