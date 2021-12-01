import defs
import utils as u
import analyser
import datetime
import threading
import v20


class Manager():
    def __init__(self, ctx,accountid,run_stream=False,ms_queue=None) -> None:

        self.ctx = ctx
        self.messages = ms_queue
        self.accountid = accountid
        self.insts = u.load_instruments()
        self.a = analyser.Analyser(self.ctx, ms_queue=ms_queue)
        self.pricetable = {}
        if run_stream:
            try:
                threading.Thread(target=self.run_pricestream).start()
            except BaseException as e:
                print('{!r}; restarting thread'.format(e))

    def move_stop_breakeven(self, t) -> None:
        piploc = u.get_piplocation(t.instrument, self.insts)
        be_pip = defs.global_params['be_pip'] * piploc
        MINWIN = 3 * piploc

        ts_dist = 1.5*defs.global_params['ts'] * \
            u.get_piplocation(t.instrument, self.insts)
        prec = u.get_displayprecision(t.instrument, self.insts)

        p = self.ctx.pricing.get(
            self.accountid,
            instruments=t.instrument).get('prices')[0]

        if t.currentUnits > 0:
            pl = p.closeoutAsk - t.price
            if pl > be_pip:
                self.messages.append(
                    f' BE:{t.instrument} {t.currentUnits} pl: {pl:.5f}pip')
            else:
                return
        if t.currentUnits < 0:
            MINWIN *= -1
            pl = t.price - p.closeoutBid
            if pl > be_pip:
                msg = f' BE:{t.instrument} {t.currentUnits} pl: {pl:.5f}pip'
            else:
                return

        sl = dict(
            price=str(f'{t.price+MINWIN:.5f}'),
            type='STOP_LOSS',
            tradeID=t.id)

        # ts = dict(
        #     distance=f'{ts_dist:.{prec}f}',
        #     tradeID=t.id)

        self.ctx.trade.set_dependent_orders(
            self.accountid,
            t.id,
            stopLoss=sl
        )
            # trailingStopLoss=ts)
        self.close_trade(t.id, int(abs(t.currentUnits)/5))

    def check_instruments(self):
        self.messages.append(f'{u.get_now()} checking instruments')

        trades = self.ctx.trade.list_open(self.accountid).get('trades')
        trades.sort(key=lambda x: (x.instrument, x.price))

        for i in defs.instruments:
            inst_trades = u.get_trades_by_instrument(trades, i)
            if len(inst_trades) == 0:
                threading.Thread(target=self.check_instrument,
                                 args=[i, 0]).start()
            else:
                if u.check_breakeven_for_position(trades, i):
                    # print(i, 'be')
                    if inst_trades[0].currentUnits > 0:
                        threading.Thread(
                            target=self.check_instrument, args=[i, 1]).start()
                    elif inst_trades[0].currentUnits < 0:
                        threading.Thread(
                            target=self.check_instrument, args=[i, -1]).start()

    def check_instrument(self, inst, positioning=None) -> str:
        try:
            msg = f' stream:{inst}'
            msg += f' B:{self.pricetable[inst]["bid"]:>8.5}'
            msg += f' A:{self.pricetable[inst]["ask"]:>8.5}'
            msg += f' S:{self.pricetable[inst]["spread"]:.5f}'
            msg += f' C:{self.pricetable[inst]["count"]:>5}'
            # print(msg)
        except KeyError as e:
            return

        piploc = u.get_piplocation(inst, self.insts)
        spread = self.pricetable[inst]["spread"] / piploc
        bid = self.pricetable[inst]["bid"]
        ask = self.pricetable[inst]["ask"]
        # pre-trade check
        if spread > defs.global_params['max_spread'] or spread == 0:           
            return None

        signal, signaltype = self.a.get_signal(inst, tf='M5')

        valid = [(-1, -1), (-1, 0), (1, 0), (1, 1)]
        if (signal, positioning) not in valid:
            return None

        sl = defs.global_params['sl']
        tp = defs.global_params['tp']
        ac = self.ctx.account.summary(self.accountid).get('account')
        units = int(ac.marginAvailable/4)
        if positioning == 0:  # azaz nincs az instrumentumon trade
            units = 10  # buoy
        if signaltype == 'XL':
            units *= 2

        if signal == 1:
            entry = ask
            stopprice = bid - sl*piploc
            profitPrice = ask + tp*piploc
        elif signal == -1:
            units *= -1
            entry = bid
            stopprice = ask + sl*piploc
            profitPrice = bid - tp*piploc

        self.place_market(inst, units, stopprice, profitPrice, signaltype)

        msg = (f'{units:>5}'
               f' {inst:>7}'
               f' {entry:>9.5f}'
               f' SL:{stopprice:>9.5f}'
               f' TP:{profitPrice:>9.5f}'
               f' A:{ask:>8.5f}/B:{bid:<8.5f}'
               f' {spread:>6.4f}')
        data_lock = threading.Lock()
        with data_lock:
            self.messages.append(msg)

    def place_market(self, inst, units, stopPrice=None, profitPrice=None, id='0'):
        prec = u.get_displayprecision(inst, self.insts)
        tsdist = defs.global_params['ts'] * u.get_piplocation(inst, self.insts)

        sl_on_fill = dict(timeInForce='GTC', price=f'{stopPrice:.{prec}f}')
        tp_on_fill = dict(timeInForce='GTC', price=f'{profitPrice:.{prec}f}')
        ts_on_fill = dict(timeInForce='GTC', distance=f'{tsdist:.{prec}f}')
        ce = dict(id=id, tag='Signal id', comment='Signal id commented')

        order = dict(
            type='MARKET',
            instrument=inst,
            units=units,
            clientExtensions=ce,
            takeProfitOnFill=tp_on_fill,
            stopLossOnFill=sl_on_fill
            # trailingStopLossOnFill=ts_on_fill
        )

        response = self.ctx.order.market(self.accountid, **order)
        id = response.get('orderFillTransaction').id
        return id

    def place_limit(self, inst, units, entryPrice, stopPrice, profitPrice):
        prec = u.get_displayprecision(inst, self.insts)
        ts_dist = (defs.global_params['ts']
                   * u.get_piplocation(inst, self.insts))

        sl_on_fill = dict(timeInForce='GTC', price=f'{stopPrice:.{prec}f}')
        tp_on_fill = dict(timeInForce='GTC', price=f'{profitPrice:.{prec}f}')
        ts_on_fill = dict(timeInForce='GTC', distance=f'{ts_dist:.{prec}f}')
        # ce = dict(
        # id='43', tag='jano client tagja', comment='Jano place limit')
        time_now = datetime.datetime.now(datetime.timezone.utc)
        delta = datetime.timedelta(seconds=280)
        time_5m = time_now + delta
        gtdTime = time_5m.isoformat()

        order = dict(
            type='LIMIT',
            instrument=inst,
            units=units,
            price=f'{entryPrice:.{prec}f}',
            timeInForce='GTD',
            gtdTime=gtdTime,
            # clientExtensions = ce,
            takeProfitOnFill=tp_on_fill,
            stopLossOnFill=sl_on_fill,
            trailingStopLossOnFill=ts_on_fill
        )

        response = self.ctx.order.limit(self.accountid, **order)
        if response.status != 201:
            print(response)
            print(response.body)

    def close_all_trades(self):
        trades = self.ctx.trade.list_open(self.accountid).get('trades')
        for t in trades:
            self.logger.info('Closing:', t.id, t.instrument, t.unrealizedPL)
            self.ctx.trade.close(self.accountid, t.id, units='ALL')

    def close_trade(self, tradeid, units: int = 0):
        if units == 0:
            self.ctx.trade.close(self.accountid, tradeid, units='ALL')
        else:
            self.ctx.trade.close(self.accountid, tradeid, units=str(units))

    def close_winners(self):
        trades = self.ctx.trade.list_open(self.accountid).get('trades')
        for t in trades:
            if t.unrealizedPL > 0:
                self.ctx.trade.close(self.accountid, t.id, units='ALL')

    def realize_profit(self, ratio=.5):
        trades = self.ctx.trade.list_open(self.accountid).get('trades')
        for t in trades:
            if t.unrealizedPL > 0.02:
                units_to_close = str(abs(int(t.currentUnits * ratio)))
                self.ctx.trade.close(self.accountid, t.id,
                                     units=units_to_close)

    def set_price_table(self, inst, bid, ask):
        if inst in self.pricetable:
            bidbase = self.pricetable[inst]['bid_base']
            askbase = self.pricetable[inst]['ask_base']
            bidchange = bid-bidbase
            askchange = ask-askbase
            count = self.pricetable[inst]['count'] + 1
            spread = ask - bid

            self.pricetable[inst] = dict(
                bid_base=bidbase,
                ask_base=askbase,
                bid=bid,
                ask=ask,
                count=count,
                bidchange=bidchange,
                askchange=askchange,
                spread=spread
            )
        else:
            self.pricetable[inst] = dict(
                bid_base=bid,
                ask_base=ask,
                bid=bid,
                ask=ask,
                count=1,
                bidchange=0,
                askchange=0,
                spread=99
            )

    def run_pricestream(self):
        ctxs = v20.Context(
            hostname='stream-fxpractice.oanda.com', token=defs.key)
        ctxs.set_header(key='Authorization', value=defs.key)
        insts = ",".join(defs.instruments)
        response = ctxs.pricing.stream(defs.ACCOUNT_ID, instruments=insts)
        self.messages.append('price stream started')
        for typ, data in response.parts():
            if typ == "pricing.ClientPrice":
                self.set_price_table(
                    data.instrument,
                    data.bids[0].price,
                    data.asks[0].price)


if __name__ == "__main__":
    ctx = v20.Context(hostname=defs.HOSTNAME, token=defs.key)
    ctx.set_header(key='Authorization', value=defs.key)
    mgr = Manager(ctx, defs.ACCOUNT_ID)
    # mgr.check_instruments()
    # mgr.close_winmers()
    # mgr.close_all_trades(defs.ACCOUNT_ID)
    # mgr.place_market('EUR_USD',100, 1.1610, 1.17)
    # mgr.add_ts()
    # mgr.manage_trades()
    # mgr.check_instrument('EUR_USD')
