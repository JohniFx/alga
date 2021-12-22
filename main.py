import cfg
import trader
import quant
from datetime import datetime

class Main():
    def __init__(self) -> None:
        cfg.price_observers.append(self)
        cfg.transaction_observers.append(self)
        cfg.account_observers.append(self)
        self.t = trader.Trader()
        self.t.check_instruments()
        # update_kpi()
        # update_tradeable_instruments()
        # check_instruments()

        # manage_positions
        # show_account


    def on_tick(self, cp):
        msg = f"{datetime.now().strftime('%H:%M:%S')}"
        msg += f" {cp['i']}: {cp['bid']:.5f} / {cp['ask']:.5f}"
        print(msg)

    def on_data(self, data):
        msg = f"{datetime.now().strftime('%H:%M:%S')}"
        inst = ''
        if hasattr(data, 'instrument'):
            inst = data.instrument
        msg += f" {data.id} {data.type} {data.reason} {inst}"
        print(msg)

    def on_account_changes(self):
        msg = f"{datetime.now().strftime('%H:%M:%S')}"
        msg+= f" {cfg.account.balance}"
        msg+= f" {cfg.account.unrealizedPL}"
        msg+= f" t:{len(cfg.account.trades)}"
        msg+= f" o:{len(cfg.account.orders)}"
        msg+= f" p:{self.get_open_positions()}"
        print(msg)

    def get_open_positions(self):
        openpos = []
        for p in cfg.account.positions:
            if p.marginUsed is not None:
                openpos.append(p)
        return len(openpos)

    def show_prices(self):
        r = cfg.ctx.pricing.get(cfg.ACCOUNT_ID, instruments='EUR_USD')
        prices = r.get('prices')
        for p in prices:
            print(p)


if __name__ == '__main__':
    m = Main()
