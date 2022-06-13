import threading
import time

class AccountPolling(threading.Thread):
    def __init__(self, account, alock, ):
        super().__init__()
        self.account = account
        self.last_id = account.lastTransactionID

    def run(self) -> None:
        while True:
            try:
                r = self.ctx.account.changes(self.ACCOUNT_ID,
                                             sinceTransactionID=_lastId)
                changes = r.get('changes')
                state = r.get('state')
                _lastId = r.get('lastTransactionID')
                self.update_account(changes, state)
            except Exception as e:
                print('Account update loop crashed', e)
            time.sleep(15)

