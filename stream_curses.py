import curses
import v20
import defs
from dateutil import parser
import os
import sys
from time import sleep

ctxs = v20.Context(hostname='stream-fxpractice.oanda.com', token=defs.key)
ctxs.set_header(key='Authorization', value=defs.key)
insts = ",".join(defs.instruments)

def curses_main(w):
    w.addstr("Streaming prices in terminal by Jano~~\n")
    w.refresh()
    curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_RED)
    curses.init_pair(4, curses.COLOR_WHITE, curses.COLOR_BLACK)
    process_data(w)


def process_data(w):
    response = ctxs.pricing.stream(defs.ACCOUNT_ID, instruments=insts)
    for typ, data in response.parts():
        if typ == "pricing.ClientPrice":
            dtime = parser.parse(data.time).strftime("%H:%M:%S")
            spread = data.asks[0].price-data.bids[0].price

            prc = f"{data.instrument} {dtime} {data.bids[0].price:>9.4f}/{data.asks[0].price:>9.4f}"

            for i, inst in zip(range(2, len(defs.instruments)+2), defs.instruments):
                if data.instrument == inst:
                    w.addstr(i, 0, prc)
                    limit = 0.0002
                    if inst.endswith('JPY'):
                        limit = 0.02
                    show_spread(w, i, 40, spread, limit)
            w.refresh()


def show_spread(w, row: int, col: int, spread: float, limit: float):
    if spread > limit:
        w.addstr(row, col, f'{spread:.5f}', curses.color_pair(3))
    else:
        w.addstr(row, col, f'{spread:.5f}', curses.color_pair(4))


if __name__ == ('__main__'):
    try:
        curses.wrapper(curses_main)
    except KeyboardInterrupt as ke:
        sys.exit(0)
    except Exception as ex:
        sleep(10)
        os.execv(sys.executable, ['python3'] + sys.argv)
    