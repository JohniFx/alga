import cfg
import utils as u
import quant
import threading
import datetime


class Trader():
    def __init__(self) -> None:
        self.initial_tradecheck()

    def do_trading(self):
        print('')
        self.initial_tradecheck()
        self.check_trades_for_breakeven()
        self.check_instruments()

    def check_instruments(self):
        ti = cfg.tradeable_instruments
        ti.insert(0, ti.pop(ti.index(Trader.get_max_instrument())))
        for i in ti:
            # TODO: adding is OK, but to open a new is not OK
            if not Trader.is_trade_allowed():
                return
            if 'spread' not in cfg.instruments[i]:
                continue
            position = self.get_trades_by_instrument(cfg.account.trades, i)
            if len(position) == 0:
                self.check_instrument(i)
            elif self.check_breakeven_for_position(cfg.account.trades, i):
                pos = 1 if position[0].currentUnits > 0 else -1
                self.check_instrument(i, pos)

    @staticmethod
    def get_max_instrument():
        pl = 0
        inst = ''
        for t in cfg.account.trades:
            if t.unrealizedPL > pl:
                pl = t.unrealizedPL
                inst = t.instrument
        return inst

    def check_breakeven_for_position(self, trades, instrument):
        all_be = []
        for t in trades:
            if t.instrument == instrument:
                for o in cfg.account.orders:
                    if o.id == t.stopLossOrderID:
                        all_be.append(
                            (t.currentUnits > 0 and o.price >= t.price)
                            or
                            (t.currentUnits < 0 and o.price <= t.price))
        if all(all_be):
            print(f'{u.get_now()} CBFP', instrument, all(all_be))
        return all(all_be)

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
            # already in b/e
            sl = u.get_order_by_id(t.stopLossOrderID)
            cu = t.currentUnits
            if ((cu > 0 and sl.price >= t.price) or
                    (cu < 0 and sl.price <= t.price)):
                continue
            if cu > 0:
                pip = cfg.instruments[t.instrument]['bid'] - t.price
            elif t.currentUnits < 0:
                pip = t.price - cfg.instruments[t.instrument]['ask']
            pip_pl = pip / \
                pow(10, cfg.instruments[t.instrument]['pipLocation'])
            print(f'{u.get_now()} NOBE: #{t.id:>5} {cu:>5.0f}',
                  f' {t.instrument}@{t.price:<8.5f} {pip_pl:>5.2f}')
            if pip_pl > cfg.global_params['be_pips']:
                print(f'{u.get_now()} MOBE: {cu:>5.0f}',
                      f' {t.instrument} {pip_pl:.2f}')
                be_sl = cfg.global_params['be_sl'] *\
                    pow(10, cfg.instruments[t.instrument]['pipLocation'])
                if t.currentUnits > 0:
                    sl_price = t.price + be_sl
                else:
                    sl_price = t.price - be_sl
                self.set_stoploss(t.id, sl_price, t.instrument)

    @ staticmethod
    def is_trade_allowed() -> bool:
        for t in cfg.account.trades:
            if t.unrealizedPL <= 0:
                print(
                    f'{u.get_now()} RULE: #{t.id:>5}',
                    f'{t.currentUnits:>5.0f}',
                    f'{t.instrument} in loss {t.unrealizedPL} wait.')
                return False
        return True

    def check_instrument(self, inst: str, positioning: int = 0) -> str:
        # print(f'{u.get_now()}  check {inst} positioning:{positioning}')
        # get signal
        signal, signaltype = quant.Quant().get_signal(inst, tf='M5')
        valid = [(-1, -1), (-1, 0), (1, 0), (1, 1)]
        if (signal, positioning) not in valid:
            return None

        sl = cfg.global_params['sl']
        tp = cfg.global_params['tp']
        units = int(cfg.account.marginAvailable/100) * signal
        if signaltype == 'XL':
            units *= 2

        ask = cfg.instruments[inst]['ask']
        bid = cfg.instruments[inst]['bid']
        spread = cfg.instruments[inst]['spread']
        # print(f"piplocation: {inst} {cfg.instruments[inst]['pipLocation']}")
        piploc = pow(10, cfg.instruments[inst]['pipLocation'])

        spread_piploc = spread / piploc
        # print(f'{u.get_now()} SPRD: {inst} {spread} {spread_piploc:.1f}')
        if spread_piploc > cfg.global_params['max_spread']:
            return

        entry = ask if signal == 1 else bid
        stopprice = entry - signal * sl * piploc
        profitPrice = entry + signal * tp * piploc

        msg = (f'{u.get_now()} OPEN {signaltype} {inst}'
               f' {units}'
               f' {entry:.5f}'
               f' SL:{stopprice:.5f}'
               f' TP:{profitPrice:>9.5f}'
               f' A:{ask:>8.5f}/B:{bid:<8.5f}'
               f' {spread:>6.4f}')
        print(msg)
        threading.Thread(
            target=self.place_market,
            args=[inst, units, stopprice, profitPrice, signaltype]).start()

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
                    self.set_stoploss(t.id, t.price, t.instrument)
                else:
                    print(u.get_now(), 'Close trade without stop')
                    self.close_trade(t)

    def check_before_stopmove(self, tradeid: int, new_sl: float):
        t = u.get_trade_by_id(tradeid)
        sl = u.get_order_by_id(t.stopLossOrderID)
        if t.currentUnits > 0 and sl.price > new_sl:
            return False
        if t.currentUnits < 0 and sl.price < new_sl:
            return False
        return True

    def set_stoploss(self, tradeid: int, price: float, inst: str):
        if not self.check_before_stopmove(tradeid, price):
            print('Pre stop move check fails:', tradeid, price)
            return
        prec = cfg.instruments[inst]['displayPrecision']
        sl = dict(
            price=f'{price:.{prec}f}',
            type='STOP_LOSS',
            tradeID=tradeid
        )
        cfg.ctx.trade.set_dependent_orders(
            cfg.ACCOUNT_ID,
            tradeid,
            stopLoss=sl
        )


if __name__ == '__main__':
    print('hi')
    # t = Trader()
    # t.check_instruments()
