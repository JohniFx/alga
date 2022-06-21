from typing import Iterable
import quant
import datetime
import v20
import threading
 

class Trader(threading.Thread):
    def __init__(self, ctx, account, insts, prices) -> None:
        super().__init__()
        self.ctx = ctx
        self.account = account
        self.instruments = insts
        self.prices = prices
        self.initial_tradecheck()

    def run(self) -> None:
        self.manage_trading()

    def manage_trading(self):
        if self.account.unrealizedPL > 35:
            self.close_all()
        for inst in self.instruments:
            trades = list(self.get_trades_by_instrument(inst))
            if len(trades) == 0:
                self.check_instrument(inst)
            if len(trades) == 1:
                self.manage_trade(trades[0])
            if len(trades) > 1:
                self.manage_position(inst)

    def manage_trade(self, t:v20.trade.TradeSummary):
        sl = self.get_order_by_id(t.stopLossOrderID)
        trailingStopValue = ''
        if t.trailingStopLossOrderID is not None:
            ts = self.get_order_by_id(t.trailingStopLossOrderID)
            trailingStopValue = ts.trailingStopValue
        print(t.instrument, f'{t.currentUnits:>5.0f} PL:{t.unrealizedPL:>6.2f} E: {t.price:>8.4f} sl: {sl.price:>8.4f} ts:{trailingStopValue}')
        if t.unrealizedPL < 0:
            return
        self.trade_breakeven(t)
        if self.is_trade_allowed():
            self.trade_scalein(t)

    def manage_position(self, inst:str):
        p = self.get_position_by_instrument(inst)
        self.position_show(inst)
        self.position_close_unbalanced(p)
        self.position_breakeven(p)
        self.position_move_ts(p)
        self.position_move_tp(p)
        if self.is_trade_allowed():
            self.position_scalein(p)

    def trade_breakeven(self, trade:v20.trade.TradeSummary):
        sl = self.get_order_by_id(trade.stopLossOrderID)
        c1 = trade.currentUnits > 0 and sl.price >= trade.price
        c2 = trade.currentUnits < 0 and sl.price <= trade.price
        if c1 or c2:
            return

        be_trigger_offset = self.get_global_params()['be_trigger'] * pow(10, self.get_piploc(trade.instrument))
        be_level_offset   = self.get_global_params()['be_level']   * pow(10, self.get_piploc(trade.instrument))
        # print(self.instruments[trade.instrument])
      
        if self.prices[trade.instrument] == {}:
            print('price still empty')
        else:
            print(f'live price: {type(self.prices[trade.instrument])}', self.prices[trade.instrument])
            print('')
        if trade.currentUnits > 0:
            # TODO: lock, get, unlock
            price = self.prices[trade.instrument].bid
            if price > (trade.price + be_trigger_offset):
                sl_price = trade.price + be_level_offset
                self.set_stoploss(trade, sl_price)
                

        if trade.currentUnits < 0:
            price = self.prices[trade.instrument].ask
            if price < (trade.price - be_trigger_offset):
                sl_price = trade.price - be_level_offset
                self.set_stoploss(trade, sl_price)

    def trade_scalein(self, t: v20.trade.TradeSummary):
        if t.stopLossOrderID is not None:
            sl = self.get_order_by_id(t.stopLossOrderID)
        if t.currentUnits > 0 and (sl.price > t.price):
            self.check_instrument(t.instrument, 1)
        if t.currentUnits < 0 and (sl.price < t.price):
            self.check_instrument(t.instrument, -1)
    
    def position_move_ts(self, p: v20.position.Position):
        pass
    
    def position_move_tp(self, p: v20.position.Position):
        pass

    def position_breakeven(self, p:v20.position.Position):
        trades = self.get_trades_by_instrument(p.instrument)
        avg_price = p.long.averagePrice if p.long.units !=0 else p.short.averagePrice
        units = p.long.units if p.long.units != 0 else p.short.units
        scaled = False
        for t in trades:
            if t.unrealizedPL < 0:
                return
            self.trade_breakeven(t)

        be_trigger_offset = self.get_global_params()['be_trigger'] * pow(10, self.get_piploc(p.instrument))
        be_level_offset   = self.get_global_params()['be_level']   * pow(10, self.get_piploc(p.instrument))

        current_price = self.instruments[p.instrument]
        if units > 0 and (current_price['bid'] > (avg_price + be_trigger_offset)):
            print(f' POSITION LONG BREAKEVEN avg_price: {avg_price} bid: {current_price["bid"]}')
            for t in trades:
                sl_price = avg_price + be_level_offset
                print(sl_price, t.id, )
                self.set_stoploss(t, sl_price)
                self.check_instrument(p.instrument)
        elif units < 0 and (current_price['ask'] < (avg_price - be_trigger_offset)):
            print(f' POSITION SHORT BREAKEVEN')
            for t in trades:
                sl_price = avg_price - be_level_offset
                self.set_stoploss(t, sl_price)
                self.check_instrument(p.instrument)

    def position_close_unbalanced(self, p: v20.position.Position):
        trades = self.get_trades_by_instrument(p.instrument)
        ps = p.long if p.long.units !=0 else p.short
        losingtrades = 0
        for t in trades:
            if t.unrealizedPL < 0:
                losingtrades += 1
        if p.unrealizedPL >= 0 and losingtrades > 2:
            print(f'closing {p.instrument}: too many negative trades')
            if ps.units > 0:
                self.ctx.position.close(self.account.id, instrument=p.instrument, longUnits='ALL')
            if ps.units < 0:
                self.ctx.position.close(self.account.id, instrument=p.instrument, shortUnits='ALL')

    def position_show(self, inst):
        p      = self.get_position_by_instrument(inst)
        trades = self.get_trades_by_instrument(inst)
        ap     = p.long.averagePrice if p.long.units !=0 else p.short.averagePrice
        print(inst, f'pl:{p.unrealizedPL:.2f} avg_price: {ap}')
        for t in trades:
            sl = self.get_order_by_id(t.stopLossOrderID)
            print(f'. {t.currentUnits:>4.0f} @ {t.price:<8.4f} pl:{t.unrealizedPL:>7.2f} sl: {sl.price}')

    def position_scalein(self, p):
        # all trade in be
        trades = self.get_trades_by_instrument(p.instrument)
        for t in trades:
            sl = self.get_order_by_id(t.stopLossOrderID)
            if t.currentUnits > 0 and (sl.price < t.price):
                return
            if t.currentUnits < 0 and (sl.price > t.price):
                return
        pos = 1  if p.long.units != 0 else -1
        print('POSITION SCALE-IN')
        self.check_instrument(p.instrument, pos)

    def check_instrument(self, inst: str, pos: int = 0):
        print(f'{inst} check. pos: {pos}')
        if not self.check_spread(inst):
            return
        signal = self.get_signal(inst, pos)
        if signal is None:
            return
        units = int(self.account.marginAvailable/100) * signal['signal']
        id = self.place_market(inst, units)
        self.save_plot(signal['df'], id)

    def check_spread(self, inst)->bool:
        # TODO: lock, getspread, unlock
        spread = 0 # self.instruments[inst]['spread']
        piploc = pow(10, self.get_piploc(inst))
        spread_piploc = spread / piploc
        if spread_piploc > self.get_global_params()['max_spread']:
            return False
        return True

    def save_plot(self, df, trade_id):    
        print('saving plot', trade_id)
    
    def get_signal(self, inst, pos):
        signal = quant.Quant(self.ctx, self.account.id, self.instruments).get_signal(inst, 15, 'M5', pos)
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
        for t in self.account.trades:
            if t.unrealizedPL <= 0:
                print(f'  RULE: {t.instrument} {t.unrealizedPL} trade is in loss.')
                return False
        return True

    def place_market(self, inst, units, sl_price=None, tp_price=None, signaltype=None, ts_dist=None):
        prec = self.instruments[inst]['displayPrecision']
        units = f'{units:.{self.instruments[inst]["tradeUnitsPrecision"]}f}'
        
        gp_sl = self.get_global_params()['sl'] * pow(10, self.get_piploc(inst))
        gp_ts = self.get_global_params()['ts'] * pow(10, self.get_piploc(inst))
        gp_tp = self.get_global_params()['tp'] * pow(10, self.get_piploc(inst))

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
            #clientExtensions=ce,
            takeProfitOnFill=tp_on_fill,
            stopLossOnFill=sl_on_fill,
            trailingStopLossOnFill=ts_on_fill
        )
        response = self.ctx.order.market(self.account.id, **order)
        try:
            id = response.get('orderFillTransaction').id
        except v20.errors.ResponseNoField as x:
            print(x)
            print(response)
            print('')
            for b in response.body:
                print(response.get(b))
                print('')

    def place_limit(self, inst, units, entryPrice, stopPrice, profitPrice):
        prec = self.instruments[inst]['displayPrecision']
        ts_dist = self.get_global_params()['ts'] * self.get_piploc(inst)
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

        response = self.ctx.order.limit(self.account.id, **order)
        if response.status != 201:
            print(response)
            print(response.body)

    def close_all(self):
        print('CLOSING ALL TRADES')
        for t in self.account.trades:
            self.close_trade(t)

    def close_trade(self, trade, units: int = 0):
        print(f'CLOSE {trade.id} {trade.instrument}')
        if units == 0:
            self.ctx.trade.close(self.account.id, trade.id, units='ALL')
        else:
            self.ctx.trade.close(self.account.id, trade.id, units=str(units))

    def check_before_stopmove(self, t: v20.trade.TradeSummary, new_sl: float):
        sl = self.get_order_by_id(t.stopLossOrderID)
        if sl is None:
            return True
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
        dp = self.instruments[trade.instrument]['displayPrecision']
        sl = dict(
            price=f'{sl_price:.{dp}f}',
            type='STOP_LOSS',
            tradeID=trade.id
        )
        self.ctx.trade.set_dependent_orders(
            self.account.id,
            trade.id,
            stopLoss=sl
        )

    def initial_tradecheck(self):
        for t in self.account.trades:
            if t.stopLossOrderID is None:
                if t.unrealizedPL >= 0:
                    self.set_stoploss(t, t.price)
                else:
                    print('Close trade without stop')
                    self.close_trade(t)

    def get_positions(self) -> Iterable:
        for p in self.account.positions:
            if p.marginUsed is not None:
                yield p

    def get_position_by_instrument(self, inst)->v20.position.Position:
        for p in self.account.positions:
            if p.marginUsed is not None:
                if p.instrument == inst:
                    return p
        return None

    def get_trades_by_instrument(self, inst) -> Iterable:
        for t in self.account.trades:
            if t.instrument == inst:
                yield t

    def get_trade_by_id(self, tradeid: int) -> v20.trade.TradeSummary:  # type: ignore
        for t in self.account.trades:
            if t.id == tradeid:
                return t

    def get_order_by_id(self, orderid: int) -> v20.order.Order:  # type: ignore
        for o in self.account.orders:
            if o.id == orderid:
                return o
    
    def get_piploc(self, inst):
        return self.instruments[inst]['pipLocation']

    def get_global_params(self): 
        import json
        with open('params.json') as json_file:
            p = json.load(json_file)
        return p