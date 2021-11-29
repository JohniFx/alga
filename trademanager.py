import v20
from v20.account import AccountChanges
import defs
import time
import manager as m
from collections import deque
import sys
import os
import curses
import schedule
import utils


class TradeManager():   
    def __init__(self, ctx) -> None:
        self.messages = []
        self.ctx = ctx
        self.accountid = defs.ACCOUNT_ID
        self.lastTransactionID = 0
        self.account = None
        self.get_account()
        self.max_loss = deque([0, 0.0], maxlen=25)
        self.lastpl = 0
        self.new_trade_count = 0

        self.mgr = m.Manager(ctx, defs.ACCOUNT_ID,
                             run_stream=True, 
                             ms_queue=self.messages)
        
        # start threads
        schedule.every(3).minutes.do(
            utils.run_threaded, self.mgr.check_instruments)

        utils.run_threaded(curses.wrapper, args=[self.run,])
        
        # initial check
        self.mgr.check_instruments()

        while True:
            schedule.run_pending()
            time.sleep(schedule.idle_seconds())
       
    def run(self, w):
        curses.start_color()
        curses.use_default_colors()
        while True:
            self.update_account()
            self.manage_trades(self.account.trades, self.account.NAV, w)
            self.show_stat(w)
            
            if len(self.account.trades) == 0:
                time.sleep(60)
            elif len(self.account.trades) < 6:
                time.sleep(40)
            else:
                time.sleep(20)

            if self.account.unrealizedPL > 3:
                self.messages.append('Profit realization')
                self.mgr.realize_profit(ratio=.2)

    def manage_trades(self, trades, nav: float, w) -> None:
        # w.reset()
        trades.sort(key=lambda x: (x.instrument))
        w.addstr(
            2, 0, f'{"id":>6} {"ccy":>7} {"units":>5} {"Entry":>8}'
            + f' {"Stop":>8} {"TS":>8} {"unr.PL":>8} {"rea.PL":>8}'
            + f' {"distan":>8} {"bid":>8} {"ask":>8}')
        w.addstr(3, 0, f'{"-"*6} {"-"*7} {"-"*5} {"-"*8} {"-"*8} {"-"*8} {"-"*8}'
                 + f' {"-"*8} {"-"*8} {"-"*7} {"-"*8} {"-"*8}')
        i = 3
        for t in trades:
            rpl = '' if t.realizedPL == 0 else str(round(t.realizedPL, 4))
            pips = t.unrealizedPL / int(t.currentUnits)
            stop = ''
            ts_value = ''
            distance = ''
            if t.instrument in self.mgr.pricetable.keys():
                bid = self.mgr.pricetable[t.instrument]['bid']
                ask = self.mgr.pricetable[t.instrument]['ask']
            else:
                continue

            for o in self.account.orders:
                if o.id == t.stopLossOrderID:
                    stop = f'{float(o.price):.4f}'
                if o.id == t.trailingStopLossOrderID:
                    ts_value = f'{float(o.trailingStopValue):.4f}'
                    distance = f'{float(o.distance):.4f}'
            
            mark = ''
            if t.unrealizedPL < min(self.max_loss):
                self.max_loss.append(t.unrealizedPL)
            if t.currentUnits == t.initialUnits \
                    and t.unrealizedPL <= -(nav * 0.0001):
                mark = 'L1'  # <= {-(nav * 0.0001):.4f}'
            if t.currentUnits <= t.initialUnits \
                    and t.unrealizedPL <= -(nav * 0.0002):
                mark = 'L2'  # <= {-(nav * 0.0002):.4f}'
            if t.currentUnits <= t.initialUnits and t.unrealizedPL <= -(nav * 0.0003):
                mark = 'L3'  # <= {-(nav * 0.0003):.4f}'
            
            ## Breakeven
            piploc = utils.get_piplocation(t.instrument, self.mgr.insts)
            be_pip = defs.global_params['be_pip'] * piploc
            if t.currentUnits > 0:
                pl = ask - t.price
                if pl > be_pip and float(stop) < t.price:
                    self.messages.append(f'L-BE: {t.instrument} A:{ask} > {t.price}')
                    self.mgr.move_stop_breakeven(t)
            if t.currentUnits < 0:
                pl = t.price - bid
                if pl > be_pip and float(stop) > t.price:
                    self.messages.append(f'S-BE: {t.instrument} B:{bid} < {t.price}')
                    self.mgr.move_stop_breakeven(t)
                

            if t.realizedPL <= 0 and t.unrealizedPL > (nav * 0.0001):
                mark = 'P1'  # > {nav * 0.0001:.4f}'
                self.mgr.move_stop_breakeven(t)

            if t.realizedPL > 0 and t.unrealizedPL > (nav * 0.0002):
                mark = 'P2'  # > {nav * 0.0002:.4f}'
            if t.realizedPL > 0 and t.unrealizedPL > (nav * 0.0003):
                mark = 'P3'  # > {nav * 0.0003:.4f}'
            if t.realizedPL > 0 and t.unrealizedPL > (nav * 0.0004):
                mark = 'P4'  # > {nav * 0.0003:.4f}'
            if t.realizedPL > 0 and t.unrealizedPL > (nav * 0.0006):
                mark = 'P5+'  # > {nav * 0.0003:.4f}'
                self.ctx.trade.close(self.accountid, t.id, units=t.currentUnits * 0.1)
                
            msg = f'{t.id} {t.instrument} {int(t.currentUnits):>5}'
            msg += f' {t.price:>8.4f}'
            msg += f' {stop:>8}'
            msg += f' {ts_value:>8}'
            msg += f' {t.unrealizedPL:>8.4f}'
            msg += f' {rpl:>8}'
            msg += f' {distance:>8}'
            msg += f' {bid:>7}'
            msg += f' {ask:>7}'
            msg += f' {pips:>8.5f}'
            i += 1
            w.addstr(i, 0, msg)
        # w.refresh()
        i+=2
        self.show_messages(w, row=i)

    def show_stat(self, w):
        if self.account.unrealizedPL > self.lastpl:
            simb = u'\u25B2'
        else:
            simb = u'\u25BC'
        stat = f'NAV:{self.account.NAV}'
        stat += f' PL:{self.account.unrealizedPL:>5.4f} {simb}'
        stat += f' DD:{min(self.max_loss):.4f}'
        stat += f' nt:{self.new_trade_count}'
        stat += f' p:{self.get_open_positions()}/{len(defs.instruments)}'
        stat += f' o:{len(self.account.orders)}'
        stat += f' t:{len(self.account.trades)}'

        w.addstr(0, 0, stat)
        w.refresh()
        self.lastpl = self.account.unrealizedPL

    def show_messages(self, w, row=17):
        for msg in self.messages:
            try:
                w.addstr(row, 0, msg)    
            except curses.error:
                pass
            row += 1
        w.clrtobot()
        w.refresh()
        self.messages.clear()

    def get_account(self) -> None:
        response = self.ctx.account.get(self.accountid)
        self.account = response.get('account')
        self.lastTransactionID = response.get('lastTransactionID')

    def update_account(self):
        r = self.ctx.account.changes(
            self.accountid,
            sinceTransactionID=self.lastTransactionID)
        changes = r.get('changes')
        state = r.get('state')
        self.lastTransactionID = r.get('lastTransactionID')
        self.apply_changes(changes)

        # update price dependent fields
        for field in state.fields():
            self.update_attribute(self.account, field.name, field.value)

        # update price dependent lists
        for tc in state.trades:
            for t in self.account.trades:
                if t.id == tc.id:
                    t.unrealizedPL = tc.unrealizedPL
                    t.marginUsed = tc.marginUsed

        for po in state.positions:
            for p in self.account.positions:
                if p.instrument == po.instrument:
                    p.netUnrealizedPL = po.netUnrealizedPL
                    p.longUnrealizedPL = po.longUnrealizedPL
                    p.shortUnrealizedPL = po.shortUnrealizedPL
                    p.marginUsed = po.marginUsed
        
        for so in state.orders:
            for o in self.account.orders:
                if o.id == so.id:
                    o.trailingStopValue = so.trailingStopValue
                    o.distance = so.triggerDistance
   
    def get_open_positions(self):
        openpos=[]
        for p in self.account.positions:
            if p.marginUsed != None:
                openpos.append(p)
        return len(openpos)

    def apply_changes(self, changes: AccountChanges):
        for to in changes.tradesOpened:
            # print(f' new trade: {to.id} {to.instrument} {to.price}')
            self.account.trades.append(to)
            self.new_trade_count +=1

        for tr in changes.tradesReduced:
            # print(f' trade reduced: {tr.id}')
            for t in self.account.trades:
                if t.id == tr.id:
                    t.currentUnits = tr.currentUnits
                    t.realizedPL = tr.realizedPL
                    t.averageClosePrice = tr.averageClosePrice

        for tc in changes.tradesClosed:
            # print(f" trade closed: {tc.id} {tc.instrument} ")
            for t in self.account.trades:
                if t.id == tc.id:
                    self.account.trades.remove(t)

        # positions
        for p in changes.positions:
            for ap in self.account.positions:
                if p.instrument == ap.instrument:
                    self.account.positions.remove(ap)
                    self.account.positions.append(p)

        # ordersCancelled: []
        for occ in changes.ordersCancelled:
            for o in self.account.orders:
                if o.id == occ.id:
                    # print(f" order Cancelled: {occ.id} {occ.tradeID} {occ.type}")
                    self.account.orders.remove(o)
                    # frissíteni a trade linket.. ha van
                    for t in self.account.trades:
                        if t.id == occ.tradeID:
                            if occ.type == 'STOP_LOSS':
                                t.stopLossOrderID = None
                            elif occ.type == 'TAKE_PROFIT':
                                t.takeProfitOrderID = None
                            elif occ.type == 'TRAILING_STOP_LOSS':
                                t.trailingStopLossOrderID = None


        # ordersCreated: []
        for ocr in changes.ordersCreated:
            # print(f" orders Created: {ocr.id} {ocr.tradeID} {ocr.type}")
            self.account.orders.append(ocr)
            # frissíteni a trade linket.. ha van
            for t in self.account.trades:
                if t.id == ocr.tradeID:
                    if ocr.type == 'STOP_LOSS':
                        t.stopLossOrderID = ocr.id
                    elif ocr.type == 'TAKE_PROFIT':
                        t.takeProfitOrderID = ocr.id
                    elif ocr.type == 'TRAILING_STOP_LOSS':
                        t.trailingStopLossOrderID = ocr.id

        # ordersFilled: []
        for ofi in changes.ordersFilled:
            for o in self.account.orders:
                if o.id == ofi.id:
                    # print(f" order Filled: {ofi.id} {ofi.tradeID} {ofi.type} ")
                    self.account.orders.remove(o)

        # ordersTriggered: []
        for otr in changes.ordersTriggered:
            for o in self.account.orders:
                if o.id == otr.id:
                    # print(f" order Triggered: {otr.id} {otr.tradeID} {otr.type}")
                    self.account.orders.remove(o)

    def update_attribute(self, dest, name, value):
        # print(name, value)
        if name in ('orders', 'trades', 'positions'):
            return
        if hasattr(dest, name) and getattr(dest, name) is not None:
            setattr(dest, name, value)


if __name__ == '__main__':
    ctx = v20.Context(hostname='api-fxpractice.oanda.com', token=defs.key)
    ctx.set_header(key='Authorization', value=defs.key)
    try:
        tm = TradeManager(ctx)
    except KeyboardInterrupt:
        os._exit(1)
        # sys.exit(0)
