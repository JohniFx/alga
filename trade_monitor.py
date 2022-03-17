#!/usr/bin/python3

from datetime import datetime
import os

cp = os.path.dirname(os.path.abspath(__file__))

with open(f'{cp}/changelog', 'a' ) as file:
    file.write(f'\n{datetime.now()} changelog')
    print(datetime.now(), 'change log updated')


# p = 17
# e = 10
# sl = 6
# be_pip = 11
# be_sl = 1

# p-e = pl
# pl = pl /pow(10, piplocation)
# pl//be_pip = pl_ratio

# if p<e:
#     return

# if p > (e + 3*be_pip):
#     stop_price = e + 4*be_sl
#     move_to_be(id, stop_price)

# if p > (e + 2*be_pip):
#     stop_price = e + 2*be_sl
#     move_to_be(id, stop_price)

# if p > (e + be_pip):
#     stop_price = e + be_sl
#     move_to_be(id, stop_price)

# def check_before_stopmove() -> bool:
#     if ok:
#         return True
#     else:
#         return False

# def move_to_be(trade, id, stop_price):
#     if not check_before_stopmove:
#         return

    # move stop
