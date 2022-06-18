import threading
from typing import Any
from log_wrapper import LogWrapper
import configparser

class StreamBase(threading.Thread):

    def __init__(self,
            events: dict[str, threading.Event], 
            lock: threading.Lock, 
            logname: str) -> None:
        super().__init__()
        self.events = events
       
        self.lock = lock
        self.log = LogWrapper(logname)

        config = configparser.ConfigParser()
        config.read('config.ini')
        self.ACCOUNT_ID = config['OANDA']['ACCOUNT_ID']
        self.SECURE_HEADER = {
            "Authorization": f"Bearer {config['OANDA']['API_KEY']}",
            "Content-Type": "application/json"}
    
    def log_message(self, msg, error=False):
        if error == True:
            self.log.logger.error(msg)
        else:            
            self.log.logger.debug(msg)

if __name__ == '__main__':
    sb = StreamBase({},  threading.Lock(), 'StreamBase')
    print(sb)
