import cfg
import v20
import utils as u
import threading
from time import sleep

class Trader():
    def __init__(self) -> None:
        sleep(5)

    def check_instruments(self):
        trades = cfg.account.trades
        trades.sort(key=lambda x: (x.instrument, x.price))

        for i in cfg.instruments:
            inst_trades = cfg.get_trades_by_instrument(trades, i)
            if len(inst_trades) == 0:
                self.check_instrument(i)
            else:
                if cfg.check_breakeven_for_position(trades, i):
                    if inst_trades[0].currentUnits > 0:
                        threading.Thread(
                            target=self.check_instrument, args=[i, 1]).start()
                    elif inst_trades[0].currentUnits < 0:
                        threading.Thread(
                            target=self.check_instrument, args=[i, -1]).start()

    def check_instrument(self, inst, positioning=None) -> str:
        signal, signaltype = self.a.get_signal(inst, tf='M5')

        valid = [(-1, -1), (-1, 0), (1, 0), (1, 1)]
        if (signal, positioning) not in valid:
            return None

        sl = cfg.global_params['sl']
        tp = cfg.global_params['tp']
        units = int(cfg.account.marginAvailable/4)

        if signaltype == 'XL':
            units *= 2

        ask = cfg.instruments['inst']['ask']
        bid = cfg.instruments['inst']['bid']
        piploc = cfg.instruments['inst']['pipLocation']
  

        if signal == 1:
            entry = ask
            stopprice = ask - sl*piploc  # spread excluded if ask - SL
            profitPrice = ask + tp*piploc
        elif signal == -1:
            units *= -1
            entry = bid
            stopprice = bid + sl*piploc
            profitPrice = bid - tp*piploc

        self.place_market(inst, units, stopprice, profitPrice, signaltype)

        msg = (f'{units:>5}'
               f' {inst:>7}'
               f' {entry:>9.5f}'
               f' SL:{stopprice:>9.5f}'
               f' TP:{profitPrice:>9.5f}'
               f' A:{ask:>8.5f}/B:{bid:<8.5f}'
               f' {spread:>6.4f}')
        data_lock = threading.Lock()
        with data_lock:
            self.messages.append(msg)

    def place_market(self, inst, units, stopPrice, profitPrice=None, id='0'):
        prec = cfg.instruments[inst]['displayPrecision']
        gp_ts = cfg.global_params['ts']
        tsdist = gp_ts * cfg.instruments[inst]['pipLocation']

        sl_on_fill = dict(timeInForce='GTC', price=f'{stopPrice:.{prec}f}')
        tp_on_fill = dict(timeInForce='GTC', price=f'{profitPrice:.{prec}f}')
        # ts_on_fill = dict(timeInForce='GTC', distance=f'{tsdist:.{prec}f}')
        ce = dict(id=id, tag='Signal id', comment='Signal id commented')

        order = dict(
            type='MARKET',
            instrument=inst,
            units=units,
            clientExtensions=ce,
            takeProfitOnFill=tp_on_fill,
            stopLossOnFill=sl_on_fill
            # trailingStopLossOnFill=ts_on_fill
        )

        response = cfg.ctx.order.market(cfg.ACCOUNT_ID, **order)
        id = response.get('orderFillTransaction').id
        return id

    def place_limit(self, inst, units, entryPrice, stopPrice, profitPrice):
        prec = cfg.instruments[inst]['displayPrecision']
        ts_dist = cfg.global_params['ts'] * cfg.instruments[inst]['pipLocation']

        sl_on_fill = dict(timeInForce='GTC', price=f'{stopPrice:.{prec}f}')
        tp_on_fill = dict(timeInForce='GTC', price=f'{profitPrice:.{prec}f}')
        ts_on_fill = dict(timeInForce='GTC', distance=f'{ts_dist:.{prec}f}')
        # ce = dict(
        # id='43', tag='jano client tagja', comment='Jano place limit')
        time_now = datetime.datetime.now(datetime.timezone.utc)
        delta = datetime.timedelta(seconds=280)
        time_5m = time_now + delta
        gtdTime = time_5m.isoformat()

        order = dict(
            type='LIMIT',
            instrument=inst,
            units=units,
            price=f'{entryPrice:.{prec}f}',
            timeInForce='GTD',
            gtdTime=gtdTime,
            # clientExtensions = ce,
            takeProfitOnFill=tp_on_fill,
            stopLossOnFill=sl_on_fill,
            trailingStopLossOnFill=ts_on_fill
        )

        response = cfg.ctx.order.limit(cfg.ACCOUNT_ID, **order)
        if response.status != 201:
            print(response)
            print(response.body)


if __name__ == '__main__':
    t = Trader()
    t.check_instruments()
