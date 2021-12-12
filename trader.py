import cfg
import v20

class Trader():
    def __init__(self) -> None:
        pass

    def check_instruments(self):
        trades = cfg.account.trades
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
        except KeyError:
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

        if signaltype == 'XL':
            units *= 2

        if signal == 1:
            entry = ask
            stopprice = ask - sl*piploc  # spread excluded if ask - SL
            profitPrice = ask + tp*piploc
        elif signal == -1:
            units *= -1
            entry = bid
            stopprice = bid + sl*piploc
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

    def place_market(self, inst, units, stopPrice, profitPrice=None, id='0'):
        prec = u.get_displayprecision(inst, self.insts)
        # gp_ts = defs.global_params['ts']
        # tsdist = gp_ts * u.get_piplocation(inst, self.insts)

        sl_on_fill = dict(timeInForce='GTC', price=f'{stopPrice:.{prec}f}')
        tp_on_fill = dict(timeInForce='GTC', price=f'{profitPrice:.{prec}f}')
        # ts_on_fill = dict(timeInForce='GTC', distance=f'{tsdist:.{prec}f}')
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


if __name__ == '__main__':
    t = Trader()
    t.check_instruments()
