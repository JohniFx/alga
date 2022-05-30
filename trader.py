import utils as u
import quant
import datetime
import v20


class Trader():
    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.initial_tradecheck()

    def manage_trading(self):
        if self.cfg.account.unrealizedPL > 25:
            self.close_all()
        for inst in self.cfg.get_tradeable_instruments():
            trades = list(self.cfg.get_trades_by_instrument(inst))
            if len(trades) == 0:
                self.check_instrument(inst)
            if len(trades) == 1:
                self.manage_trade(trades[0])
            if len(trades) > 1:
                self.manage_position(inst)

    def manage_trade(self, t:v20.trade.TradeSummary):
        print(t.instrument, f'PL: {t.unrealizedPL:>6.2f}')
        if t.unrealizedPL < 0:
            return
        self.trade_breakeven(t)
        if self.is_trade_allowed():
            self.trade_scalein(t)

    def manage_position(self, inst:str):
        p = self.cfg.get_position_by_instrument(inst)
        self.position_show(inst)
        self.position_close_unbalanced(p)
        self.position_breakeven(p)
        self.position_move_ts(p)
        self.position_move_tp(p)
        if self.is_trade_allowed():
            self.position_scalein(p)

    def trade_breakeven(self, trade:v20.trade.TradeSummary):
        sl = self.cfg.get_order_by_id(trade.stopLossOrderID)
        c1 = trade.currentUnits > 0 and sl.price >= trade.price
        c2 = trade.currentUnits < 0 and sl.price <= trade.price
        if c1 or c2:
            return

        be_trigger_offset = self.cfg.get_global_params()['be_trigger'] * pow(10, self.cfg.get_piploc(trade.instrument))
        be_level_offset   = self.cfg.get_global_params()['be_level']   * pow(10, self.cfg.get_piploc(trade.instrument))

        if trade.currentUnits > 0:
            price = self.cfg.instruments[trade.instrument]['bid']
            if price > (trade.price + be_trigger_offset):
                sl_price = trade.price + be_level_offset
                self.set_stoploss(trade, sl_price)

        if trade.currentUnits < 0:
            price = self.cfg.instruments[trade.instrument]['ask']
            if price < (trade.price - be_trigger_offset):
                sl_price = trade.price - be_level_offset
                self.set_stoploss(trade, sl_price)

    def trade_scalein(self, t: v20.trade.TradeSummary):
        sl = self.cfg.get_order_by_id(t.stopLossOrderID)
        if t.currentUnits > 0 and (sl.price > t.price):
            print('TRADE Scale in long ')
            self.check_instrument(t.instrument, 1)
        if t.currentUnits < 0 and (sl.price < t.price):
            print('TRADE Scale in short')
            self.check_instrument(t.instrument, -1)
    
    def position_move_ts(self, p: v20.position.Position):
        pass
    
    def position_move_tp(self, p: v20.position.Position):
        pass

    def position_breakeven(self, p:v20.position.Position):
        trades = self.cfg.get_trades_by_instrument(p.instrument)
        avg_price = p.long.averagePrice if p.long.units !=0 else p.short.averagePrice
        units = p.long.units if p.long.units != 0 else p.short.units
        scaled = False
        for t in trades:
            if t.unrealizedPL < 0:
                return
            self.trade_breakeven(t)
            self.trade_scalein(t)

        current_price = self.cfg.instruments[p.instrument]
        if units > 0:
            current_price['bid'] > (avg_price + self.cfg.get_global_params()['be_pips']* pow(10, self.cfg.get_piploc(p.instrument)))
            print(f' POSITION LONG BREAKEVEN avg_price: {avg_price} bid: {current_price["bid"]}')
            for t in trades:
                sl_price = avg_price + self.cfg.get_global_params()['be_sl'] * pow(10, self.cfg.get_piploc(p.instrument))
                print(sl_price, t.id, )
                self.set_stoploss(t, sl_price)
        if units < 0:
            current_price['ask'] < (avg_price - self.cfg.get_global_params()['be_pips']* pow(10, self.cfg.get_piploc(p.instrument)))
            print(f' POSITION SHORT BREAKEVEN')
            for t in trades:
                sl_price = avg_price - self.cfg.get_global_params()['be_sl'] * pow(10, self.cfg.get_piploc(p.instrument))
                self.set_stoploss(t, sl_price)

    def position_close_unbalanced(self, p: v20.position.Position):
        trades = self.cfg.get_trades_by_instrument(p.instrument)
        ps = p.long if p.long.units !=0 else p.short
        losingtrades = 0
        for t in trades:
            if t.unrealizedPL < 0:
                losingtrades += 1
        if p.unrealizedPL >= 0 and losingtrades > 2:
            print(f'closing {p.instrument}: too many negative trades')
            if ps.units > 0:
                self.cfg.ctx.position.close(self.cfg.ACCOUNT_ID, instrument=p.instrument, longUnits='ALL')
            if ps.units < 0:
                self.cfg.ctx.position.close(self.cfg.ACCOUNT_ID, instrument=p.instrument, shortUnits='ALL')

    def position_show(self, inst):
        p      = self.cfg.get_position_by_instrument(inst)
        trades = self.cfg.get_trades_by_instrument(inst)
        ap     = p.long.averagePrice if p.long.units !=0 else p.short.averagePrice
        print(inst, f'pl:{p.unrealizedPL:.2f} avg_price: {ap}')
        for t in trades:
            sl = self.cfg.get_order_by_id(t.stopLossOrderID)
            print(f'. {t.currentUnits:>4.0f} @ {t.price:<8.4f} pl:{t.unrealizedPL:>7.2f} sl: {sl.price}')

    def position_scalein(self, p):
        # TODO: if long and  current_price > average_price
        pass 

    def check_instrument(self, inst: str, pos: int = 0):
        # print(f'{inst} check. pos: {positioning}')
        signal = self.get_signal(inst, pos)
        if signal is None:
            return

        # pre-trade
        units = int(self.cfg.account.marginAvailable/100) * signal['signal']
        sl = self.cfg.get_global_params()['sl']
        tp = self.cfg.get_global_params()['tp']
        
        spread = self.cfg.instruments[inst]['spread']
        piploc = pow(10, self.cfg.get_piploc(inst))
        #
        spread_piploc = spread / piploc
        if spread_piploc > self.cfg.get_global_params()['max_spread']:
            return
        #
        entry = ask if signal['signal'] == 1 else bid
        stopprice = entry - signal['signal'] * sl * piploc
        profitPrice = entry + signal['signal'] * tp * piploc
        #
        msg = (f' {inst} OPEN {signal["signaltype"]} '
               f' {units}'
               f' {entry:.5f}'
               f' {spread:>6.5f}')
        print(msg)
        self.place_market(inst, units, stopprice, profitPrice, 'S3', signal['ts_dist'])
    
    def get_signal(self, inst, pos):
        signal = quant.Quant(self.cfg).get_signal(inst, 15, 'M5', pos)
        if signal is None:
            return None
        valid = [(-1, -1), (-1, 0), (1, 0), (1, 1)]
        if (signal['signal'], pos) not in valid:
            return None
        return signal

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

    def place_market(self, inst, units, sl_price, tp_price=None, signaltype='0', ts_dist=0):
        prec = self.cfg.instruments[inst]['displayPrecision']
        
        gp_sl = self.cfg.get_global_params()['sl'] * pow(10, self.cfg.get_piploc(inst))
        gp_ts = self.cfg.get_global_params()['ts'] * pow(10, self.cfg.get_piploc(inst))
        gp_tp = self.cfg.get_global_params()['tp'] * pow(10, self.cfg.get_piploc(inst))

        sl_on_fill = dict(
            timeInForce='GTC', 
            # price=f'{sl_price:.{prec}f}',
            distance=f'{gp_sl:.{prec}f}')

        tp_on_fill = dict(
            timeInForce='GTC', 
            #price=f'{tp_price:.{prec}f}',
            distance=f'{gp_tp:.{prec}f}')

        ts_on_fill = dict(
            timeInForce='GTC', 
            distance=f'{gp_ts:.{prec}f}')

        ce = dict(id=signaltype, tag='Signal tag', comment='Signal comment')
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

    def check_before_stopmove(self, t: v20.trade.TradeSummary, new_sl: float):
        sl = self.cfg.get_order_by_id(t.stopLossOrderID)
        if t.currentUnits > 0 and sl.price > new_sl:
            print(f'FAIL: {t.currentUnits} sl.price: {sl.price} > new_sl:{new_sl:.5f}')
            return False
        if t.currentUnits < 0 and sl.price < new_sl:
            print(f'FAIL: {t.currentUnits} sl.price: {sl.price} < new_sl:{new_sl:.5f}')
            return False
        return True

    def set_stoploss(self, trade: v20.trade.TradeSummary, sl_price: float):
        if not self.check_before_stopmove(trade, sl_price):
            print(f'Pre stop move check fails: #{trade.id}')
            return
        #
        dp = self.cfg.instruments[trade.instrument]['displayPrecision']
        sl = dict(
            price=f'{sl_price:.{dp}f}',
            type='STOP_LOSS',
            tradeID=trade.id
        )
        self.cfg.ctx.trade.set_dependent_orders(
            self.cfg.ACCOUNT_ID,
            trade.id,
            stopLoss=sl
        )

    def initial_tradecheck(self):
        for t in self.cfg.account.trades:
            if t.stopLossOrderID is None:
                if t.unrealizedPL >= 0:
                    self.set_stoploss(t, t.price)
                else:
                    print(u.get_now(), 'Close trade without stop')
                    self.close_trade(t)


if __name__ == '__main__':
    import main
    t = Trader(main.Main())
    t.check_instruments()
