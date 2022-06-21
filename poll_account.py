import threading
import time
from configparser import ConfigParser
import v20
from log_wrapper import LogWrapper

class AccountPolling(threading.Thread):
    def __init__(self, account, event, lock, logname, ctx):
        super().__init__()
        self.account = account
        self.event = event
        self.lock = lock
        self.ctx = ctx
        self.account_id = account.id
        self.last_id = self.account.lastTransactionID
        self.log = LogWrapper(logname)

    def update_account(self,
                       changes: v20.account.AccountChanges,
                       state: v20.account.AccountChangesState):
        
        self.apply_changes(changes)
        self.apply_transactions(changes)
        # #
        self.update_fields(state)
        self.update_trades(state)
        self.update_positions(state)
        self.update_orders(state)
    
    def run(self) -> None:
        _lastId = self.account.lastTransactionID
        i = 0

        while True:
            try:
                r = self.ctx.account.changes(self.account_id, sinceTransactionID=_lastId)
                changes = r.get('changes')
                state = r.get('state')
                _lastId = r.get('lastTransactionID')
                self.update_account(changes, state)
                print(f'#{i:>3}: {self.account.NAV:.2f} {self.account.unrealizedPL}')
                i+=1
                time.sleep(20)
            except v20.errors.V20Timeout as e:
                print('account error: ',e)
            except Exception as e:
                print('account error: ',e)
    
    def apply_changes(self, changes: v20.account.AccountChanges):
        # Trades Opened
        for to in changes.tradesOpened:
            to.isLong = False
            if to.currentUnits > 0:
                to.isLong = True
            self.account.trades.append(to)
        # Trades Reduced
        for tr in changes.tradesReduced:
            for t in self.account.trades:
                if t.id == tr.id:
                    t.currentUnits = tr.currentUnits
                    t.realizedPL = tr.realizedPL
                    t.averageClosePrice = tr.averageClosePrice
        # Trades Closed
        for tc in changes.tradesClosed:
            for t in self.account.trades:
                if t.id == tc.id:
                    self.account.trades.remove(t)
        #
        for cp in changes.positions:
            for ap in self.account.positions:
                if ap.instrument == cp.instrument:
                    self.account.positions.remove(ap)
                    self.account.positions.append(cp)
        #
        for occ in changes.ordersCancelled:
            for o in self.account.orders:
                if o.id == occ.id:
                    self.account.orders.remove(o)
                    for t in self.account.trades:
                        if t.id == occ.tradeID:
                            if occ.type == 'STOP_LOSS':
                                t.stopLossOrderID = None
                            elif occ.type == 'TAKE_PROFIT':
                                t.takeProfitOrderID = None
                            elif occ.type == 'TRAILING_STOP_LOSS':
                                t.trailingStopLossOrderID = None
        #
        for ocr in changes.ordersCreated:
            self.account.orders.append(ocr)
            for t in self.account.trades:
                # AttributeError: 'StopOrder' object has no attribute 'tradeID'
                if t.id == ocr.tradeID:
                    if ocr.type == 'STOP_LOSS':
                        t.stopLossOrderID = ocr.id
                    elif ocr.type == 'TAKE_PROFIT':
                        t.takeProfitOrderID = ocr.id
                    elif ocr.type == 'TRAILING_STOP_LOSS':
                        t.trailingStopLossOrderID = ocr.id
        #
        for ofi in changes.ordersFilled:
            for o in self.account.orders:
                if o.id == ofi.id:
                    self.account.orders.remove(o)
        #
        for otr in changes.ordersTriggered:
            for o in self.account.orders:
                if o.id == otr.id:
                    self.account.orders.remove(o)
    
    def apply_transactions(self, changes):
        for tr in changes.transactions:
            if tr.type == 'ORDER_FILL':
                self.account.balance = tr.accountBalance

    def update_trades(self, state):
        for st in state.trades:
            for at in self.account.trades:
                if at.id == st.id:
                    at.unrealizedPL = st.unrealizedPL
                    at.marginUsed = st.marginUsed

    def update_fields(self, state):
        for field in state.fields():
            self.update_attribute(self.account, field.name, field.value)

    def update_attribute(self, dest, name, value):
        if name in ('orders', 'trades', 'positions'):
            return
        if hasattr(dest, name) and getattr(dest, name) is not None:
            setattr(dest, name, value)

    def update_positions(self, state: v20.account.AccountChangesState):
        for sp in state.positions:
            for p in self.account.positions:
                if p.instrument == sp.instrument:
                    p.unrealizedPL = sp.netUnrealizedPL
                    p.long.unrealizedPL = sp.longUnrealizedPL
                    p.short.unrealizedPL = sp.shortUnrealizedPL
                    p.marginUsed = sp.marginUsed

    def update_orders(self, state):
        for so in state.orders:
            for o in self.account.orders:
                if o.id == so.id:
                    o.trailingStopValue = so.trailingStopValue
                    o.distance = so.triggerDistance

if __name__ == '__main__':
    config = ConfigParser()
    config.read('config.ini')
    API_KEY = config['OANDA']['API_KEY']
    account_id = config['OANDA']['ACCOUNT_ID']
    HOSTNAME = "api-fxpractice.oanda.com"
    key = f'Bearer {API_KEY}'
    ctx = v20.Context(hostname=HOSTNAME, token=key)
    ctx.set_header(key='Authorization', value=key)

    account = ctx.account.get(account_id).get('account')
    event = threading.Event()
    lock = threading.Lock()

    ap = AccountPolling(account, event, lock, "Account", ctx)
    ap.daemon = True
    ap.start()
    print(account.NAV)
    try:
        ap.join()
        
    except KeyboardInterrupt as error:
        print('KI error')
    

