import requests
import threading
import json
from stream_base import StreamBase

class TransactionStream(StreamBase):
    def __init__(self,events,lock,logname  ): 
        super().__init__(events, lock, logname)
        
    def on_data(self, trdata):
        print(trdata)


    def run(self) -> None:
        print('start transaction stream')
        url = f"https://stream-fxpractice.oanda.com/v3/accounts/{self.ACCOUNT_ID}/transactions/stream"
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
    