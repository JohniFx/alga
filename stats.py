import json
import datetime as dt

class Stat():

    def __init__(self):
        self.s = self.load()
        if self.s is None:
            self.s = self.create()
            self.dump()

    def load(self):
        try:
            f = open('stats.json','r')
            s = json.load(f)
        except OSError as e:
            print('No stats file')
            s = self.create()
        except Exception as x:
            print(x)

        return s


    def create(self) -> dict:
        s = dict(
            created=str(dt.datetime.now()),
            count_sl=0,
            count_ts=0,
            count_tp=0,
            sum_sl=0,
            sum_ts=0,
            sum_tp=0,
            count_manual=0,
            sum_manual=0,
            count_be = 0,
            count_pos_closout=0,
            sum_pos_closout=0
        )
        return s

    def update(self, data):
        if data.reason == 'TAKE_PROFIT_ORDER':
            self.s['count_tp'] += 1
            self.s['sum_tp'] += data.pl
        elif data.reason == 'STOP_LOSS_ORDER':
            self.s['count_sl'] += 1
            self.s['sum_sl'] += data.pl
        elif data.reason == 'TRAILING_STOP_LOSS_ORDER':
            self.s['count_ts'] += 1
            self.s['sum_ts'] += data.pl
        elif data.reason == 'MARKET_ORDER_TRADE_CLOSE':
            self.s['count_manual'] += 1
            self.s['sum_manual'] += data.pl
        elif data.reason == 'MARKET_ORDER_POSITION_CLOSEOUT':
            self.s['count_pos_closout'] += 1
            self.s['sum_pos_closout'] += data.pl
        self.dump()

    def dump(self):
        with open('stats.json', 'w') as f:
            json.dump(self.s, f, indent=2)

    def show(self):
        print(f" sl: {self.s['count_sl']}/{self.s['sum_sl']:.2f}",
              f" ts: {self.s['count_ts']}/{self.s['sum_ts']:.2f}",
              f" tp: {self.s['count_tp']}/{self.s['sum_tp']:.2f}",
              f" mt: {self.s['count_manual']}/{self.s['sum_manual']:.2f}")

if __name__ == '__main__':
    s = Stat()
    s.show()
