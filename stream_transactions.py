import v20
import defs
from dateutil import parser
import os
import sys
import time

__version__ = '2021-12-04'

ctxs = v20.Context(hostname='stream-fxpractice.oanda.com', token=defs.key)
ctxs.set_header(key='Authorization', value=defs.key)

response = ctxs.transaction.stream(defs.ACCOUNT_ID)

for typ, data in response.parts():
    print(typ, data)