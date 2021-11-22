import feed as f
import defs
import pandas as pd
import numpy as np
import pprint as pp

import matplotlib.pyplot as plt
%matplotlib inline

import v20

import statistics
accountID = f.accountID
from datetime import datetime
from dateutil import parser
import time
print(datetime.now())

# create context
ctx = v20.Context(hostname= 'api-fxpractice.oanda.com', token=defs.key)
ctx.set_header(key='Authorization', value=defs.key)
# streaming contenxt
ctxs=v20.Context(hostname='stream-fxpractice.oanda.com', token=defs.key)
ctxs.set_header(key='Authorization', value=defs.key)


resp = ctx.transaction.since(accountID = defs.ACCOUNT_ID, id=129000)

lastid = resp.get('lastTransactionID')
transactions = resp.get('transactions')


def get_transaction(id):
    for t in transactions:
        if str(t.id) == id:
            return t
    return None

trade_hist = []
for t in transactions:
    if hasattr(t, 'tradesClosed'):
        if t.tradesClosed is not None:
            x = get_transaction(t.tradesClosed[0].tradeID)
            if x is not None:
                tradehist=dict(
                closeid=t.id,
                instrument=t.instrument, 
                units=x.units, 
                entry=x.price,
                exit=t.price,
                pl=t.pl, 
                reason=t.reason,
                tradeid =x.id,
                orderid=x.orderID, 
                signal=x.clientOrderID)
                trade_hist.append(tradehist)

df = pd.DataFrame(trade_hist)

df.groupby(['reason', 'signal']).pl.mean().unstack().round(2)


