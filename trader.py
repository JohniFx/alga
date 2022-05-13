import cfg
import utils as u
import quant
import threading
import datetime
import v20


class Trader():
    def __init__(self) -> None:
        self.initial_tradecheck()

    def do_trading(self):
        cfg.account.trades.sort(key=lambda x: x.unrealizedPL, reverse=True)
        #
        print('Check positions')
        self.check_positions()
        #
        print('Check trades')
        self.check_trades()
        #
        print('Check instruments')
        self.check_instruments()
        #
        cfg.print_account()

    def check_positions(self):
        if len(cfg.account.trades) < cfg.account.openPositionCount:
            return
        #
        positions = cfg.ctx.position.list_open(cfg.ACCOUNT_ID).get('positions')
        positions = sorted(positions, key=lambda position: position.unrealizedPL, reverse=True)
        #
        for p in positions:
            ps = None
            if p.long.units > 0 and len(p.long.tradeIDs) > 1:
                ps = p.long
            if p.short.units < 0 and len(p.short.tradeIDs) > 1:
                ps = p.short
            if ps is not None:
                print(f'{p.instrument} pl:{p.unrealizedPL:<5.2f} ap:{ps.averagePrice:>10.5f}')
                #
                trades = cfg.ctx.trade.list(accountID=cfg.ACCOUNT_ID, instrument=p.instrument).get('trades')
                trades = sorted(trades, key=lambda trade: trade.unrealizedPL, reverse=False)
                # TODO: ezeket a szabályokat külön metodusba
                ## Close position if too many negative trades
                losingtrades = 0
                for t in trades:
                    print(f'\t {t.currentUnits:.0f}@{t.price:>8.4f} pl:{t.unrealizedPL:>7.4f} sl:{t.stopLossOrder.price:>8.4f}')
                    if t.unrealizedPL < 0:
                        losingtrades += 1
                if p.unrealizedPL >= 0 and losingtrades > 2:
                    print(f'closing {p.instrument}: too many negative trades')
                    if ps.units > 0:
                        cfg.ctx.position.close(cfg.ACCOUNT_ID, instrument=p.instrument, longUnits='ALL')
                    if ps.units < 0:
                        cfg.ctx.position.close(cfg.ACCOUNT_ID, instrument=p.instrument, shortUnits='ALL')
                #
                # TODO: move all trades stop to position level breakeven
                #
                ## Scale in new trades
                if self.check_breakeven_for_position(cfg.account.trades, p.instrument):
                    print('Possible scale in', i)
                    pos = 1 if ps.units > 0 else -1
                    self.check_instrument(i, pos)

    def check_trades(self):
        for t in cfg.account.trades:
            if t.unrealizedPL <= 0:
                continue
            #
            pip_pl = self.get_pip_pl(t.instrument, t.currentUnits, t.price)
            if pip_pl is None:
                return
            #
            # trade already in B/E > check to add
            if self.is_be(t, u.get_order_by_id(t.stopLossOrderID)):
                self.print_trade(t, 'B/E+', pip_pl)
                # try to add
                if self.get_position(t.instrument).unrealizedPL > 0:
                    pos = 1 if t.currentUnits > 0 else -1
                    self.check_instrument(t.instrument, pos)
                continue
            # trade green but not yet b/e
            if pip_pl > cfg.global_params['be_pips']:
                self.print_trade(t, 'MOBE', pip_pl)
                be_sl = cfg.global_params['be_sl'] * pow(10, cfg.get_piploc(t.instrument))
                if t.currentUnits > 0:
                    sl_price = t.price + be_sl
                else:
                    sl_price = t.price - be_sl
                self.set_stoploss(t.id, sl_price, t.instrument)

    def check_instruments(self):
        if not Trader.is_trade_allowed():
            return
        for i in cfg.tradeable_instruments:
            trades = cfg.ctx.trade.list(cfg.ACCOUNT_ID, instrument=i).get('trades')
            if len(trades) == 0:
                self.check_instrument(i, 0)

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
        return all(all_be)

    def check_instrument(self, inst: str, positioning: int = 0) -> str:
        # print(f'{u.get_now()} {inst} pos: {positioning}')
        signal = quant.Quant().get_signal(inst, 15, 'M5', positioning)
        valid = [(-1, -1), (-1, 0), (1, 0), (1, 1)]
        if (signal['signal'], positioning) not in valid:
            return None
        #
        sl = cfg.global_params['sl']
        tp = cfg.global_params['tp']
        units = int(cfg.account.marginAvailable/100) * signal['signal']
        #
        try:
            ask = cfg.instruments[inst]['ask']
        except KeyError as k:
            print(inst, positioning, k)
            return
        bid = cfg.instruments[inst]['bid']
        spread = cfg.instruments[inst]['spread']
        piploc = pow(10, cfg.get_piploc(inst))
        #
        spread_piploc = spread / piploc
        # print(f'{u.get_now()} SPRD: {inst} {spread} {spread_piploc:.1f}')
        if spread_piploc > cfg.global_params['max_spread']:
            return
        #
        entry = ask if signal['signal'] == 1 else bid
        stopprice = entry - signal['signal'] * sl * piploc
        profitPrice = entry + signal['signal'] * tp * piploc
        #
        msg = (f'{u.get_now()} OPEN {signal["signaltype"]} {inst}'
               f' {units}'
               f' {entry:.5f}'
               #    f' SL:{stopprice:.5f}'
               #    f' TP:{profitPrice:>9.5f}'
               #    f' A:{ask:>8.5f}/B:{bid:<8.5f}'
               f' {spread:>6.5f}')
        print(msg)
        self.place_market(inst, units, stopprice, profitPrice, 'S3', signal['ts_dist'])
        # threading.Thread(
        #     target=self.place_market,
        #     args=[inst, units, stopprice, profitPrice, signal['signaltype'], signal['ts_dist']]).start()

    def get_distance_from_sl(self, trade: v20.trade):
        sl = u.get_order_by_id(trade.stopLossOrderID)
        bid = cfg.instruments[trade.instrument]['bid']
        ask = cfg.instruments[trade.instrument]['ask']
        if trade.currentUnits > 0:
            dist_from_sl = bid - sl.price
        if trade.currentUnits < 0:
            dist_from_sl = sl.price - ask
        print(f'{u.get_now()} {trade.currentUnits} {trade.instrument}',
              f'sl: {sl.price} dist from SL:{dist_from_sl:.5f} bid:{bid} ask:{ask}')
        return dist_from_sl

    def get_distance_from_entry(self, trade):
        pass

    def is_be(self, t, sl):
        c1 = t.currentUnits > 0 and sl.price >= t.price
        c2 = t.currentUnits < 0 and sl.price <= t.price
        return True if c1 or c2 else False

    @staticmethod
    def DEL_get_max_instrument():
        pl = 0
        inst = 'EUR_USD'
        for t in cfg.account.trades:
            if t.unrealizedPL > pl:
                pl = t.unrealizedPL
                inst = t.instrument
        return inst

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
        try:
            if cu > 0:
                pip = cfg.instruments[inst]['bid'] - price
            if cu < 0:
                pip = price - cfg.instruments[inst]['ask']
        except KeyError as ke:
            print('keyerror:', inst, ke)
            return None
        return pip / pow(10, cfg.get_piploc(inst))

    @ staticmethod
    def is_trade_allowed() -> bool:
        h = datetime.datetime.now().hour
        if 6 < h < 21:
            return True
        #
        for t in cfg.account.trades:
            if t.unrealizedPL <= 0:
                print(
                    f'{u.get_now()} RULE: #{t.id:>5}',
                    f'{t.currentUnits:>5.0f}',
                    f'{t.instrument} in loss {t.unrealizedPL} wait.')
                return False
        return True

    def place_market(self, inst, units, stopPrice, profitPrice=None, signaltype='0', ts_dist=0):
        prec = cfg.instruments[inst]['displayPrecision']
        gp_ts = cfg.global_params['ts']
        tsdist = gp_ts * pow(10, cfg.get_piploc(inst))
        if ts_dist > tsdist:
            tsdist = ts_dist
        sl_on_fill = dict(timeInForce='GTC', price=f'{stopPrice:.{prec}f}')
        tp_on_fill = dict(timeInForce='GTC', price=f'{profitPrice:.{prec}f}')
        ts_on_fill = dict(timeInForce='GTC', distance=f'{tsdist:.{prec}f}')
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
        response = cfg.ctx.order.market(cfg.ACCOUNT_ID, **order)
        id = response.get('orderFillTransaction').id
        return id

    def place_limit(self, inst, units, entryPrice, stopPrice, profitPrice):
        prec = cfg.instruments[inst]['displayPrecision']
        ts_dist = cfg.global_params['ts'] * cfg.get_piploc(inst)
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

    def initial_tradecheck(self):
        for t in cfg.account.trades:
            if t.stopLossOrderID is None:
                if t.unrealizedPL >= 0:
                    self.set_stoploss(t.id, t.price, t.instrument)
                else:
                    print(u.get_now(), 'Close trade without stop')
                    self.close_trade(t)

    def get_position(self, inst):
        for p in cfg.account.positions:
            if p.instrument == inst:
                return p


if __name__ == '__main__':
    print('hi')
    # t = Trader()
    # t.check_instruments()
