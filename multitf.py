from schedule import repeat, every, run_pending
from time import sleep
import utils as u
import threading

print(u.get_now(), 'Test starts')
instruments = ['EUR_USD', 'GBP_USD']


@repeat(every(2).minutes)
def scan_5m():
    print(u.get_now(), '5m scanner')
    print('got a result start new scan')
    for i in instruments:
        threading.Thread(target=scan_30s, args=[i, ]).start()
        threading.Thread(target=scan_30s, args=[i, 15]).start()
    print('5M scan finished')


def scan_30s(inst: str, freq: int = 30):
    for i in range(5):
        print(u.get_now(), f'{freq} scanner:', inst,
              threading.current_thread().ident)
        sleep(freq)


scan_5m()

while True:
    run_pending()
    sleep(1)
