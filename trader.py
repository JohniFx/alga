import utils as u
import quant
import datetime
import v20


class Trader():
    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.initial_tradecheck()
        self.hot_insts = []

    def do_trading_simu(self):
        for i in self.cfg.get_tradeable_instruments():
            print(i)

    def do_trading(self):
        if self.cfg.account.unrealizedPL > 25:
            self.close_all()
        #
        print('Checking positions')
        self.check_positions()
        #
        print('Checking trades')
        self.check_trades()
        #
        print('Checking instruments')
        self.check_instruments()
        #
        self.cfg.print_account()

    def check_positions(self):
        for p in self.cfg.get_positions():
            td = p.long.tradeIDs if p.long.units !=0 else p.short.tradeIDs
            if len(td)>1:
                units = p.long.units if p.long.units != 0 else p.short.units
                ap = p.long.averagePrice if p.long.units !=0 else p.short.averagePrice
                print(f' {p.instrument} {units:5.0f} {p.unrealizedPL: 7.4f} {ap:>10.5f} {p.marginUsed:5.2f}')
                self.rule_close_unbalanced_position(p)
                if self.check_breakeven_for_position(p.instrument):
                    print(' Position scale in', p.instrument)
                    pos = 1 if p.long.units != 0 else -1
                    self.check_instrument(p.instrument, pos)

    def rule_close_unbalanced_position(self, p):
        trades = self.cfg.get_trades_by_instrument(p.instrument)
        ps = p.long if p.long.units !=0 else p.short
        losingtrades = 0
        for t in trades:
            print(f'{t.currentUnits:>4.0f} @ {t.price:<8.4f} pl:{t.unrealizedPL:>7.2f}')
            if t.unrealizedPL < 0:
                losingtrades += 1
        if p.unrealizedPL >= 0 and losingtrades > 2:
            print(f'closing {p.instrument}: too many negative trades')
            if ps.units > 0:
                self.cfg.ctx.position.close(self.cfg.ACCOUNT_ID, instrument=p.instrument, longUnits='ALL')
            if ps.units < 0:
                self.cfg.ctx.position.close(self.cfg.ACCOUNT_ID, instrument=p.instrument, shortUnits='ALL')

    def check_trades(self):
        self.hot_insts = []
        for t in self.cfg.account.trades:
            sl = self.cfg.get_order_by_id(t.stopLossOrderID)
            print(f'  {t.instrument} {t.currentUnits:5.0f} {t.unrealizedPL:7.4f} E:{t.price:>8.4f} SL:{sl.price:>8.4f}')
            self.hot_insts.append(t.instrument)
            if t.unrealizedPL <= 0:
                continue
            pip_pl = self.get_pip_pl(t.instrument, t.currentUnits, t.price)
            # trade already in B/E
            if self.is_be(t):
                # move stop
                if (pip_pl // self.cfg.get_global_params()['be_pips']) > 1:
                    self.print_trade(t, 'MOSL', pip_pl)
                    # d_sl = self.get_distance_from_sl(t)
                    r = pip_pl/self.cfg.get_global_params()['be_pips']
                    self.move_stop(t, pip_pl, r)
                # try to add
                if self.get_position(t.instrument).unrealizedPL > 0:
                    if self.is_trade_allowed():
                        self.print_trade(t, 'ADDD', pip_pl)
                        pos = 1 if t.currentUnits > 0 else -1
                        self.check_instrument(t.instrument, pos)
                continue
            # trade green but not yet b/e
            if pip_pl > self.cfg.get_global_params()['be_pips']:
                self.print_trade(t, 'MOBE', pip_pl)
                self.move_stop(t, pip_pl)

    def check_instruments(self):
        if not self.is_trade_allowed():
            return
        # flat instruments only
        for i in self.cfg.get_tradeable_instruments():
            if i not in self.hot_insts:
                self.check_instrument(i, 0)

    def move_stop(self, t, pip_pl, r=1):
        be_sl = r * self.cfg.get_global_params()['be_sl'] * pow(10, self.cfg.get_piploc(t.instrument))
        if t.currentUnits > 0:
            sl_price = t.price + be_sl
        else:
            sl_price = t.price - be_sl
        self.set_stoploss(t.id, sl_price, t.instrument)

    def check_breakeven_for_position(self, inst: str) -> bool:
        all_be = []
        trades = self.cfg.get_trades_by_instrument(inst)
        for t in trades:
            sl = self.cfg.get_order_by_id(t.stopLossOrderID)
            if t.currentUnits > 0 and sl.price > t.price:
                all_be.append(True)
                continue
            if t.currentUnits < 0 and sl.price < t.price:
                all_be.append(True)
                continue
            all_be.append(False)
        return all(all_be)

    def check_instrument(self, inst: str, positioning: int = 0) -> str:
        # print(f'{u.get_now()} {inst} pos: {positioning}')
        signal = quant.Quant(self.cfg).get_signal(inst, 15, 'M5', positioning)
        if signal is None:
            return
        valid = [(-1, -1), (-1, 0), (1, 0), (1, 1)]
        if (signal['signal'], positioning) not in valid:
            return None
        #
        sl = self.cfg.get_global_params()['sl']
        tp = self.cfg.get_global_params()['tp']
        units = int(self.cfg.account.marginAvailable/100) * signal['signal']
        #
        try:
            ask = self.cfg.instruments[inst]['ask']
        except KeyError as k:
            print(inst, positioning, k)
            return
        bid = self.cfg.instruments[inst]['bid']
        spread = self.cfg.instruments[inst]['spread']
        piploc = pow(10, self.cfg.get_piploc(inst))
        #
        spread_piploc = spread / piploc
        # print(f'{u.get_now()} SPRD: {inst} {spread} {spread_piploc:.1f}')
        if spread_piploc > self.cfg.get_global_params()['max_spread']:
            return
        #
        entry = ask if signal['signal'] == 1 else bid
        stopprice = entry - signal['signal'] * sl * piploc
        profitPrice = entry + signal['signal'] * tp * piploc
        #
        msg = (f'{u.get_now()} OPEN {signal["signaltype"]} {inst}'
               f' {units}'
               f' {entry:.5f}'
               f' {spread:>6.5f}')
        print(msg)
        self.place_market(inst, units, stopprice, profitPrice, 'S3', signal['ts_dist'])

    def get_distance_from_sl(self, trade: v20.trade.Trade):
        sl = u.get_order_by_id(trade.stopLossOrder.id)
        bid = self.cfg.instruments[trade.instrument]['bid']
        ask = self.cfg.instruments[trade.instrument]['ask']
        if trade.currentUnits > 0:
            dist_from_sl = bid - sl.price
        if trade.currentUnits < 0:
            dist_from_sl = sl.price - ask
        return dist_from_sl

    def is_be(self, t: v20.trade.TradeSummary) -> bool:
        sl = self.cfg.get_order_by_id(t.stopLossOrderID)
        c1 = t.currentUnits > 0 and sl.price >= t.price
        c2 = t.currentUnits < 0 and sl.price <= t.price
        return True if c1 or c2 else False

    def get_trades_by_instrument(self, trades, instrument):
        inst_trades = []
        for t in trades:
            if t.instrument == instrument:
                inst_trades.append(t)
        return inst_trades

    def print_trade(self, trade, kwrd: str, pip_pl: float):
        print(f'',
              f'{kwrd}: #{trade.id:>5}',
              f'{trade.currentUnits:>5.0f}',
              f'{trade.instrument} {trade.price:>10.5f}',
              f'{pip_pl:>5.2f}')

    def get_pip_pl(self, inst: str, cu: int, price: float) -> float:
        # distance from entry price
        try:
            if cu > 0:
                pip = self.cfg.instruments[inst]['bid'] - price
            if cu < 0:
                pip = price - self.cfg.instruments[inst]['ask']
        except KeyError as ke:
            print('keyerror:', inst, ke)
            print(self.cfg.instruments[inst])
            return None
        return pip / pow(10, self.cfg.get_piploc(inst))

    def is_trade_allowed(self) -> bool:
        h = datetime.datetime.now().hour
        if 6 < h < 21:
            return True
        #
        for t in self.cfg.account.trades:
            if t.unrealizedPL <= 0:
                print(f'  RULE: {t.instrument} {t.unrealizedPL} trade is in loss.')
                return False
        return True

    def place_market(self, inst, units, stopPrice, profitPrice=None, signaltype='0', ts_dist=0):
        prec = self.cfg.instruments[inst]['displayPrecision']
        gp_ts = self.cfg.get_global_params()['ts']* pow(10, self.cfg.get_piploc(inst))
        sl_on_fill = dict(timeInForce='GTC', price=f'{stopPrice:.{prec}f}')
        tp_on_fill = dict(timeInForce='GTC', price=f'{profitPrice:.{prec}f}')
        ts_on_fill = dict(timeInForce='GTC', distance=f'{gp_ts:.{prec}f}')
        ce = dict(id=signaltype, tag='Signal id', comment='Signal id commented')
        #
        order = dict(
            type='MARKET',
            instrument=inst,
            units=units,
            clientExtensions=ce,
            takeProfitOnFill=tp_on_fill,
            stopLossOnFill=sl_on_fill,
            trailingStopLossOnFill=ts_on_fill
        )
        response = self.cfg.ctx.order.market(self.cfg.ACCOUNT_ID, **order)
        try:
            id = response.get('orderFillTransaction').id
        except v20.errors.ResponseNoField as x:
            print(x)
            print(response)

    def place_limit(self, inst, units, entryPrice, stopPrice, profitPrice):
        prec = self.cfg.instruments[inst]['displayPrecision']
        ts_dist = self.cfg.get_global_params()['ts'] * self.cfg.get_piploc(inst)
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

        response = self.cfg.ctx.order.limit(self.cfg.ACCOUNT_ID, **order)
        if response.status != 201:
            print(response)
            print(response.body)

    def close_all(self):
        print('CLOSING ALL TRADES')
        for t in self.cfg.account.trades:
            self.close_trade(t)

    def close_trade(self, trade, units: int = 0):
        print(f'{u.get_now()} CLOSE {trade.id} {trade.instrument}')
        if units == 0:
            self.cfg.ctx.trade.close(self.cfg.ACCOUNT_ID, trade.id, units='ALL')
        else:
            self.cfg.ctx.trade.close(self.cfg.ACCOUNT_ID, trade.id, units=str(units))

    def check_before_stopmove(self, tradeid: int, new_sl: float):
        t = self.cfg.get_trade_by_id(tradeid)
        if t is None:
            return False
        sl = self.cfg.get_order_by_id(t.stopLossOrderID)
        if t.currentUnits > 0 and sl.price > new_sl:
            # print(f'FAIL: {t.currentUnits}sl.price: {sl.price} > new_sl:{new_sl:.5f}')
            return False
        if t.currentUnits < 0 and sl.price < new_sl:
            # print(f'FAIL: {t.currentUnits}sl.price: {sl.price} < new_sl:{new_sl.5f}')
            return False
        return True

    def set_stoploss(self, tradeid: int, price: float, inst: str):
        if not self.check_before_stopmove(tradeid, price):
            # print('Pre stop move check fails:', tradeid, price)
            return
        prec = self.cfg.instruments[inst]['displayPrecision']
        sl = dict(
            price=f'{price:.{prec}f}',
            type='STOP_LOSS',
            tradeID=tradeid
        )
        self.cfg.ctx.trade.set_dependent_orders(
            self.cfg.ACCOUNT_ID,
            tradeid,
            stopLoss=sl
        )

    def initial_tradecheck(self):
        for t in self.cfg.account.trades:
            if t.stopLossOrderID is None:
                if t.unrealizedPL >= 0:
                    self.set_stoploss(t.id, t.price, t.instrument)
                else:
                    print(u.get_now(), 'Close trade without stop')
                    self.close_trade(t)

    def get_position(self, inst) -> v20.position.Position:
        for p in self.cfg.account.positions:
            if p.instrument == inst:
                return p


if __name__ == '__main__':
    import main
    t = Trader(main.Main())
    t.check_instruments()
