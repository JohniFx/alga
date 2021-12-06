import cfg
import trader
import quant
from datetime import datetime

class Main():
    def __init__(self) -> None:
        # update from lnx

        # background activitites
        cfg.price_observers.append(self)
        cfg.transaction_observers.append(self)
        print(cfg.account.balance)

        # update_kpi()
        # check_instruments
        # manage_positions
        # show_account

    def on_tick(self, cp):
        msg = f"{datetime.now().strftime('%H:%M:%S')}"
        msg+= f" {cp['i']}: {cp['bid']:.5f} / {cp['ask']:.5f}"
        print(msg)

    def on_data(self, data):
        print(data)

    def schedule_tasks(self):
        pass


    def show_prices(self):
        r = cfg.ctx.pricing.get(cfg.ACCOUNT_ID, instruments='EUR_USD')
        prices = r.get('prices')
        for p in prices:
            print(p)


if __name__ == '__main__':
    m = Main()
    m.show_prices()
