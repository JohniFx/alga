import cfg
import v20
import utils as u
import quant
from time import sleep
import threading


class Trader():
    def __init__(self) -> None:
        self.initial_tradecheck()
        self.a = quant.Quant()

    def do_trading(self):
        print(f'')
        self.check_trades_for_breakeven()
        if self.is_trade_allowed(): 
            self.check_instruments()

    def check_instruments(self):
        for i in cfg.tradeable_instruments:
            if 'spread' not in cfg.instruments[i]: 
                continue

            position = self.get_trades_by_instrument(cfg.account.trades, i)

            if len(position) == 0:
                self.check_instrument(i)
            else:
                if self.check_breakeven_for_position(cfg.account.trades, i):
                    pos = 1 if position[0].currentUnits > 0 else -1
                    self.check_instrument(i, pos)

    def check_breakeven_for_position(self, trades, instrument):
        all_breakeven = []
        for t in trades:
            if t.instrument == instrument:
                for o in cfg.account.orders:
                    if o.id == t.stopLossOrderID:
                        all_breakeven.append(
                            (t.currentUnits > 0 and o.price >= t.price)
                            or
                            (t.currentUnits < 0 and o.price <= t.price))
        if all(all_breakeven):
            print(f'{u.get_now()} cfg check breakeven',
                  instrument, all(all_breakeven))
        return all(all_breakeven)

    def get_trades_by_instrument(self, trades, instrument):
        inst_trades = []
        for t in trades:
            if t.instrument == instrument:
                inst_trades.append(t)
        return inst_trades

    def check_trades_for_breakeven(self):
        for t in cfg.account.trades:
            if t.unrealizedPL <= 0:
                continue

            trade = dict(
                instrument=t.instrument,
                currentUnits=t.currentUnits,
                unrealizedPL=t.unrealizedPL)
            for o in cfg.account.orders:
                if o.id == t.stopLossOrderID:
                    trade['sl'] = o
                if o.id == t.trailingStopLossOrderID:
                    trade['ts'] = o

            long_be = t.currentUnits > 0 and trade['sl'].price >= t.price
            shrt_be = t.currentUnits < 0 and trade['sl'].price <= t.price
            if long_be or shrt_be:
                print(f'{u.get_now()} INBE: trade #{t.id:>5} {t.instrument}')
                continue

            pip_pl = pip / pow(10, cfg.instruments[t.instrument]['pipLocation'])
            if t.currentUnits > 0:
                pip = cfg.instruments[t.instrument]['bid'] - t.price
            elif t.currentUnits < 0:
                pip = t.price - cfg.instruments[t.instrument]['ask']
            print(f'{u.get_now()} NOBE: {t.currentUnits:>5.0f} {t.instrument}@{t.price} {pip_pl:.2f}')

            if pip_pow > 12:
                print(f'{u.get_now()} MOBE {t.instrument}')
                self.set_stoploss(t.id, str(t.price))

    def is_trade_allowed(self) -> bool:
        # if there is a negative trade
        for t in cfg.account.trades:
            if t.unrealizedPL <= 0:
                print(
                    f'{u.get_now()} RULE: #{t.id} {t.currentUnits:.0f} {t.instrument} in loss {t.unrealizedPL} wait.')
                return False
        return True

    def check_instrument(self, inst, positioning=0) -> str:
        print(f'{u.get_now()}  check {inst} positioning:{positioning}')
        signal, signaltype = self.a.get_signal(inst, tf='M5')

        valid = [(-1, -1), (-1, 0), (1, 0), (1, 1)]
        if (signal, positioning) not in valid:
            return None

        sl = cfg.global_params['sl']
        tp = cfg.global_params['tp']
        units = int(cfg.account.marginAvailable/100)

        if signaltype == 'XL':
            units *= 2
        ask = cfg.instruments[inst]['ask']
        bid = cfg.instruments[inst]['bid']
        spread = cfg.instruments[inst]['spread']
        piploc = pow(10, cfg.instruments[inst]['pipLocation'])

        if signal == 1:
            entry = ask
            stopprice = ask - sl*piploc  # spread excluded if ask - SL
            profitPrice = ask + tp*piploc
        elif signal == -1:
            units *= -1
            entry = bid
            stopprice = bid + sl*piploc
            profitPrice = bid - tp*piploc

        msg = (f'{u.get_now()} {signaltype} {inst}'
               f' {units}'
               f' {entry:.5f}'
               f' SL:{stopprice:.5f}'
               f' TP:{profitPrice:>9.5f}'
               f' A:{ask:>8.5f}/B:{bid:<8.5f}'
               f' {spread:>6.4f}')
        print(msg)
        threading.Thread(target=self.place_market, args=[
                         inst, units, stopprice, profitPrice, signaltype]).start()
        # self.place_market(inst, units, stopprice, profitPrice, signaltype)

    def place_market(self, inst, units, stopPrice, profitPrice=None, id='0'):
        prec = cfg.instruments[inst]['displayPrecision']
        gp_ts = cfg.global_params['ts']
        tsdist = gp_ts * pow(10, cfg.instruments[inst]['pipLocation'])

        sl_on_fill = dict(timeInForce='GTC', price=f'{stopPrice:.{prec}f}')
        tp_on_fill = dict(timeInForce='GTC', price=f'{profitPrice:.{prec}f}')
        ts_on_fill = dict(timeInForce='GTC', distance=f'{tsdist:.{prec}f}')
        ce = dict(id=id, tag='Signal id', comment='Signal id commented')

        order = dict(
            type='MARKET',
            instrument=inst,
            units=units,
            clientExtensions=ce,
            takeProfitOnFill=tp_on_fill,
            stopLossOnFill=sl_on_fill,
            trailingStopLossOnFill=ts_on_fill
        )
        # print('\n', order)

        response = cfg.ctx.order.market(cfg.ACCOUNT_ID, **order)
        id = response.get('orderFillTransaction').id
        return id

    def place_limit(self, inst, units, entryPrice, stopPrice, profitPrice):
        prec = cfg.instruments[inst]['displayPrecision']
        ts_dist = cfg.global_params['ts'] * \
            cfg.instruments[inst]['pipLocation']

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

    def close_trade(self, trade, units: int = 0):
        print(f'{u.get_now()} CLOSE {trade.id} {trade.instrument}')
        if units == 0:
            cfg.ctx.trade.close(cfg.ACCOUNT_ID, trade.id, units='ALL')
        else:
            cfg.ctx.trade.close(cfg.ACCOUNT_ID, trade.id, units=str(units))

    def initial_tradecheck(self):
        for t in cfg.account.trades:
            if t.stopLossOrderID is None:
                if t.unrealizedPL >= 0:
                    self.t.set_stoploss(t.id, str(t.price))
                else:
                    print(u.get_now(), 'Close trade without stop')
                    self.t.close_trade(t)

    def set_stoploss(self, tradeid:int, price:str):
        sl = dict(
            price=price,
            type='STOP_LOSS',
            tradeID=tradeid
        )
        cfg.ctx.trade.set_dependent_orders(
            cfg.ACCOUNT_ID,
            tradeid,
            stopLoss=sl
        )


if __name__ == '__main__':
    t = Trader()
    t.check_instruments()
