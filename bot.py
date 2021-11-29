import sys
import os
import schedule
from time import sleep
import v20
import threading
import analyser
import defs
import manager
import json
import utils as u


class TradingBot():

    def __init__(self) -> None:
        self.ctx = v20.Context(hostname=defs.HOSTNAME, token=defs.key)
        self.ctx.set_header(key='Authorization', value=defs.key)
        self.accountid = defs.ACCOUNT_ID
        # self.m = manager.Manager(self.ctx, self.accountid)

    def set_schedule(self, func, start, stop, step):
        for i in range(start, stop, step):
            p = ':{}'.format(str(i).zfill(2))
            schedule.every().hour.at(p).do(u.run_threaded, func)

    def run(self):
        schedule.clear()
        # self.set_schedule(self.m.check_instruments, 0, 60, 5)


        schedule.every().hour.at('54:10').do(
            u.run_threaded, self.fetch_data, args=['M5', 100])
        schedule.every().hour.at('54:30').do(
            u.run_threaded, self.update_kpi_file, args=[])
        schedule.every().day.at('01:15').do(
            u.run_threaded, self.fetch_data, args=['D', 2])

        while True:
            schedule.run_pending()
            sleep(schedule.idle_seconds())

    def fetch_data(self, tf='M5', count=100):
        a = analyser.Analyser(self.ctx)

        for inst in defs.instruments:
            df = a.get_candles(inst, count, tf)
            df.to_pickle(f'./data/{inst}_{tf}.pkl')
        print(u.get_now(), 'data update:', tf, count)

    def update_kpi_file(self):
        a = analyser.Analyser(self.ctx)
        kpi_data = []
        for inst in defs.instruments:
            kpi_data.append(a.get_kpi_dict(inst=inst, tf='M5'))
        with open('kpi_data.json', 'w') as write_file:
            json.dump(kpi_data, write_file, indent=2)
        print(u.get_now(), 'kpi data updated')

    def reload_modules(self):
        # print(u.get_now(), 'reloading modules')
        import importlib
        importlib.reload(defs)
        importlib.reload(manager)
        importlib.reload(analyser)

        self.m = manager.Manager(self.ctx, self.accountid)
        self.run()


if __name__ == '__main__':
    t = TradingBot()
    # print('initial data update')
    # t.fetch_data()
    # t.fetch_data(tf='D', count=10)
    # print('Kpi update')
    # t.update_kpi_file()
    try:
        # t.m.check_instruments()
        t.run()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        print('error + restart', e)
        if t is not None:
            t.run()
        else:
            print('object meghalt.. restart:')
            os.execv(sys.executable, ['python3'] + sys.argv)
