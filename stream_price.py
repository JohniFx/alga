from typing import Any
from stream_base import StreamBase
import requests
import threading
from log_wrapper import LogWrapper
from live_price import LivePrice
import json

class PriceStream(StreamBase):
    def __init__(self,
            events: dict[str, threading.Event], 
            lock: threading.Lock, 
            logname: str,
            prices: dict[str, Any] 
            ) -> None:
        super().__init__(events, lock, logname)
        self.insts = prices.keys()
        self.prices = prices

    def update_live_price(self, live_price:LivePrice):
        try:
            self.lock.acquire()
            #print(live_price)
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
        try:
            resp = requests.get(url, params=params, headers=self.SECURE_HEADER, stream=True)
        except Exception as e:
            self.log_message(f'request error: {e}')
        print('Price Streaming starts...')
        for p in resp.iter_lines():
            if p: 
                try:
                    dp = json.loads(p.decode('utf-8'))                
                    if 'type' in dp and dp['type'] == 'PRICE':
                        self.update_live_price(LivePrice(dp))
                except json.decoder.JSONDecodeError as e:
                    self.log_message(f'json.decoder {e}')


if __name__ == '__main__':
    instruments = ['EUR_USD', 'GBP_USD']

    events = {}
    prices = {}
    for i in instruments:
        prices[i] = {}
    lock = threading.Lock()
    ps = PriceStream(events,lock, "PriceStream", prices)
    ps.start()
