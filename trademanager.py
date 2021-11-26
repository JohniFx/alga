import v20
from v20.account import AccountChanges
import defs
import time
import manager as m
from collections import deque
import sys
import os
import curses


class TradeManager():   
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.accountid = defs.ACCOUNT_ID
        self.lastTransactionID = 0
        self.account = None
        self.get_account()
        self.mgr = m.Manager(ctx, defs.ACCOUNT_ID)
        self.max_loss = deque([0, 0.0], maxlen=25)
        self.lastpl = 0
        self.new_trade_count = 0
        
        curses.wrapper(self.run)
        
    def run(self, w):
        curses.start_color()
        curses.use_default_colors()
        while True:
            w.erase()
            self.update_account()
            self.manage_trades(self.account.trades, self.account.NAV, w)
            if self.account.unrealizedPL > self.lastpl:
                simb = u'\u25B2'
            else:
                simb = u'\u25BC'
            stat =f'NAV:{self.account.NAV}'
            stat += f' PL:{self.account.unrealizedPL:>5.4f} {simb}'
            stat += f' DD:{min(self.max_loss):.4f}'
            stat += f' nt:{self.new_trade_count}'
            stat += f' p:{self.get_open_positions()}/{len(defs.instruments)}'
            stat += f' o:{len(self.account.orders)}  '

            w.addstr(0, 0, stat)
            w.refresh()
            
            self.lastpl = self.account.unrealizedPL
            
            if len(self.account.trades) == 0:
                time.sleep(60)
            elif len(self.account.trades) < 6:
                time.sleep(30)
            else:
                time.sleep(10)
            if self.account.unrealizedPL > 3:
                print('Profit realization')
                self.mgr.realize_profit(ratio=.2)

    def manage_positions(self, positions):
        for p in positions:
            print(p)
            break
    
    def manage_trades(self, trades, nav: float, w) -> None:
        trades.sort(key=lambda x: (x.instrument))
        w.addstr(
            2, 0, f'{"id":>6} {"ccy":>7} {"units":>5} {"Entry":>8}'
            + f' {"Stop":>8} {"TS":>8} {"unr.PL":>8} {"rea.PL":>8}'
            + f' {"distan":>8}')
        w.addstr(3, 0, f'{"-"*6} {"-"*7} {"-"*5} {"-"*8} {"-"*8} {"-"*8} {"-"*8}'
                 + f' {"-"*8} {"-"*8} {"-"*5} {"-"*8}')
        i = 3
        for t in trades:
            mark = ''
            # nav_pc = f'{(t.unrealizedPL / nav):.5f}'
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
                
            rpl = '' if t.realizedPL == 0 else str(round(t.realizedPL, 4))
            pips = t.unrealizedPL / int(t.currentUnits)
            stop = ''
            ts_value = ''
            distance = ''
            for o in self.account.orders:
                if o.id == t.stopLossOrderID:
                    stop = f'{float(o.price):.4f}'
                if o.id == t.trailingStopLossOrderID:
                    ts_value = f'{float(o.trailingStopValue):.4f}'
                    distance = f'{float(o.distance):.4f}'

            msg = f'{t.id} {t.instrument} {int(t.currentUnits):>5}'
            msg += f' {t.price:>8.4f}'
            msg += f' {stop:>8}'
            msg += f' {ts_value:>8}'
            msg += f' {t.unrealizedPL:>8.4f}'
            msg += f' {rpl:>8}'
            msg += f' {distance:>8}'
            msg += f' {mark:>5}'
            msg += f' {pips:>8.5f}'
            i += 1
            w.addstr(i, 0, msg)
        w.refresh()

    def get_account(self) -> None:
        response = self.ctx.account.get(self.accountid)
        self.account = response.get('account')
        self.lastTransactionID = response.get('lastTransactionID')
        # print(f'Account: {self.account.NAV} last-id:{self.lastTransactionID}')
        # print(f'Open trades: {len(self.account.trades)}')

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
        sys.exit(0)
