import curses
import v20
import defs
from dateutil import parser
import os
import sys
import time

ctxs = v20.Context(hostname='stream-fxpractice.oanda.com', token=defs.key)
ctxs.set_header(key='Authorization', value=defs.key)
insts = ",".join(defs.instruments)
pricetable = {}


def curses_main(w):
    w.addstr("Streaming prices in terminal by Jano~~\n")
    w.refresh()
    curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_RED)
    curses.init_pair(4, curses.COLOR_WHITE, curses.COLOR_BLACK)
    process_data(w)

def reset_price_table():
    for k in pricetable.keys():
        pricetable[k]['count'] = 0


def set_price_table(inst, bid, ask):
    if inst in pricetable:
        bidbase = pricetable[inst]['bid_base']
        askbase = pricetable[inst]['ask_base']
        bidchange = bid-bidbase
        askchange = ask-askbase
        count = pricetable[inst]['count']+1
        spread = ask-bid

        pricetable[inst] = dict(
            bid_base=bidbase,
            ask_base=askbase,
            bid=bid,
            ask=ask,
            count=count,
            bidchange=bidchange,
            askchange=askchange,
            spread = spread
        )
    else:
        spread = ask-bid
        pricetable[inst] = dict(
            bid_base=bid,
            ask_base=ask,
            bid=bid,
            ask=ask,
            count=1,
            bidchange=0,
            askchange=0,
            spread=spread
        )


def process_data(w):
    response = ctxs.pricing.stream(defs.ACCOUNT_ID, instruments=insts)
    for typ, data in response.parts():
        if typ == "pricing.ClientPrice":
            if (time.localtime().tm_min % 15) == 0 and (time.localtime().tm_sec <10):
                reset_price_table()
            set_price_table(data.instrument,
                            data.bids[0].price, data.asks[0].price)
            dtime = parser.parse(data.time).strftime("%H:%M:%S")
            spread = data.asks[0].price-data.bids[0].price

            prc = f'{data.instrument} {dtime}'
            prc += f' {data.bids[0].price:>9.4f}/{data.asks[0].price:>9.4f}'
            prc += f' {pricetable[data.instrument]["count"]:>5}'
            prc += f' {pricetable[data.instrument]["bidchange"]:>9.4f}'

            for i, inst in zip(range(2, len(defs.instruments)+2), defs.instruments):
                if data.instrument == inst:
                    w.addstr(i, 0, prc)
                    limit = 0.0002
                    if inst.endswith('JPY'):
                        limit = 0.02
                    show_spread(w, i, 55, spread, limit)
            w.refresh()


def show_spread(w, row: int, col: int, spread: float, limit: float):
    if spread > limit:
        w.addstr(row, col, f'{spread:.5f}', curses.color_pair(3))
    else:
        w.addstr(row, col, f'{spread:.5f}', curses.color_pair(4))


if __name__ == ('__main__'):
    try:
        curses.wrapper(curses_main)
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception:
        time.sleep(10)
        os.execv(sys.executable, ['python3'] + sys.argv)
