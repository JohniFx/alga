import requests
import threading
import json
from stream_base import StreamBase

class TransactionStream(StreamBase):
    def __init__(self,events,lock,logname  ): 
        super().__init__(events, lock, logname)
        self.lastTransactionID = 0
        
    def on_data(self, d):
        
        if d['type'] == 'HEARTBEAT':
            if self.lastTransactionID != d.get('lastTransactionID'):
                print(f"{d['type']} {d.get('lastTransactionID')} {d.get('time')}")
                self.lastTransactionID = d.get('lastTransactionID')
        elif d['type']== 'MARKET_ORDER':
            print(f"{d['type']} {d.get('reason')} {d.get('instrument')} {d.get('units')} {d.get('stopLossOnFill')}")
        elif d['type']== 'ORDER_FILL':
            print(f"{d['type']} {d.get('reason')} {d.get('instrument')} {d.get('units')} {d.get('price')} {d.get('pl')}")
        elif d['type'] in ['TAKE_PROFIT_ORDER','STOP_LOSS_ORDER', 'TRAILING_STOP_LOSS_ORDER']:
            print(f"{d['type']} {d.get('reason')} {d.get('instrument')} {d.get('tradeID')} {d.get('distance')} {d.get('pl')}")
        elif d['type'] == 'ORDER_CANCEL' and d['type'] == 'LINKED_TRADE_CLOSED':
            pass
        elif d['type'] == 'DAILY_FINANCING':
            print(f"{d['type']} {d['financing']}")
        else:
            print(d)
            print('')


    def run(self) -> None:
        print('start transaction stream')
        url = f"https://stream-fxpractice.oanda.com/v3/accounts/{self.ACCOUNT_ID}/transactions/stream"

        resp = requests.Response()
        try:
            resp = requests.get(url, headers=self.SECURE_HEADER, stream=True)
        except Exception as e:
            self.log_message(f'request error: {e}')

        for p in resp.iter_lines():
            if p: 
                try:
                    dp = json.loads(p.decode('utf-8'))
                    self.on_data(dp)              
                except json.decoder.JSONDecodeError as e:
                    self.log_message(f'json.decoder {e}')

if __name__ == '__main__':
    events = threading.Event()
    lock = threading.Lock()
    tr = TransactionStream(events, lock, "Transaction")
    tr.start()

    try:
        tr.join()
    except KeyboardInterrupt as error:
        print('Keyboard interrupted')
    