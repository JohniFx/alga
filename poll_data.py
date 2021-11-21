from os import readlink
import v20
from v20.account import AccountChanges
import defs
import time
import manager as m
from collections import deque
import sys


class TradeManager():
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.accountid = defs.ACCOUNT_ID
        self.lastTransactionID = 0
        self.account = None
        self.get_account()
        self.mgr = m.Manager(ctx, defs.ACCOUNT_ID)
        self.max_loss = deque([0, 0.0], maxlen=25)
        while True:
            self.update_account()
            self.manage_trades(self.account.trades, self.account.NAV)
            print(f'NAV: {self.account.NAV}'
                  + f' PL:{self.account.unrealizedPL:>5}'
                  + f' Max DD: {min(self.max_loss):.4f}\n')
            # self.manage_positions(self.account.positions)
            if len(self.account.trades) == 0:
                time.sleep(90)
            else:
                time.sleep(30)
            if self.account.unrealizedPL > 1:
                self.mgr.close_all_trades()

    def manage_positions(self, positions):
        for p in positions:
            print(p)
            break

    def manage_trades(self, trades, nav: float) -> None:
        trades.sort(key=lambda x: (x.id))
        for t in trades:
            mark = ''
            nav_pc = f'{(t.unrealizedPL / nav):.5f}'
            if t.unrealizedPL < min(self.max_loss):
                self.max_loss.append(t.unrealizedPL)
            if t.currentUnits == t.initialUnits and t.unrealizedPL <= -(nav * 0.0001):
                mark = f'L1'# <= {-(nav * 0.0001):.4f}'
            if t.currentUnits <= t.initialUnits and t.unrealizedPL <= -(nav * 0.0002):
                mark = f'L2'# <= {-(nav * 0.0002):.4f}'
            if t.currentUnits <= t.initialUnits and t.unrealizedPL <= -(nav * 0.0003):
                mark = f'L3'# <= {-(nav * 0.0003):.4f}'

            if t.realizedPL <= 0 and t.unrealizedPL > (nav * 0.0001):
                mark = 'P1'# > {nav * 0.0001:.4f}'
                self.mgr.move_stop_breakeven(t)
            if t.realizedPL > 0 and t.unrealizedPL > (nav * 0.0002):
                mark = 'P2'  # > {nav * 0.0002:.4f}'
            if t.realizedPL > 0 and t.unrealizedPL > (nav * 0.0003):
                mark = 'P3'  # > {nav * 0.0003:.4f}'
            if t.realizedPL > 0 and t.unrealizedPL > (nav * 0.0004):
                mark = 'P4'  # > {nav * 0.0003:.4f}'
            if t.realizedPL > 0 and t.unrealizedPL > (nav * 0.0005):
                mark = 'P5+'  # > {nav * 0.0003:.4f}'
            rpl = '' if t.realizedPL == 0 else str(round(t.realizedPL, 4))
            print(
                f'{t.id}'
                + f' {t.instrument}'
                + f' {int(t.currentUnits):>5}'
                + f' {t.price:>10.5f}'
                + f' {t.unrealizedPL:>8.4f}'
                + f' {rpl:>8}'
                + f' {nav_pc:>8}'
                + f' {mark:<20}')

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
                    p.marginused = po.marginUsed

    def apply_changes(self, changes: AccountChanges):
        for to in changes.tradesOpened:
            print(f' new trade: {to.id} {to.instrument} {to.price}')
            self.account.trades.append(to)

        for tr in changes.tradesReduced:
            print(f' trade reduced: {tr.id}')
            for t in self.account.trades:
                if t.id == tr.id:
                    t.currentUnits = tr.currentUnits
                    t.realizedPL = tr.realizedPL
                    t.averageClosePrice = tr.averageClosePrice

        for tc in changes.tradesClosed:
            print(f" trade closed: {tc.id} {tc.instrument} ")
            for t in self.account.trades:
                if t.id == tc.id:
                    self.account.trades.remove(t)

        # print('update positions')
        for p in changes.positions:
            for ap in self.account.positions:
                if p.instrument == ap.instrument:
                    self.account.positions.remove(ap)
                    self.account.positions.append(p)

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
    except KeyboardInterrupt as ke:
        sys.exit(0)
