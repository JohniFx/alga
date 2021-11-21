import numpy as np
import pandas as pd
import json
import logging


class Analyser():
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.logger = logging.getLogger('bot.analyser')

    # referencing an issue
    # closing
    def get_candles(self, inst, count=15, timeframe='M5'):
        params = dict(
            price='MBA',
            granularity=timeframe,
            count=count)

        candles = self.ctx.instrument.candles(inst, **params).get('candles')

        rows = []
        for c in candles:
            c = c.dict()
            row = {}
            row['complete'] = c['complete']
            row['time'] = pd.to_datetime(c['time']).strftime("%Y-%m-%d %H:%M")
            row['volume'] = c['volume']
            for p in ['mid', 'bid', 'ask']:
                for oh in 'ohlc':
                    row[f'{p}_{oh}'] = float(c[p][oh])
            rows.append(row)

        return pd.DataFrame.from_dict(rows)

    def get_linreg(self, df):
        x = np.arange(len(df))
        y = list(df.mid_c.values)
        z = np.polyfit(x, y, deg=1)
        slope = z[0]
        intercept = z[1]
        return slope, intercept

    def add_mom(self, df, period=10):
        df['mom'] = df.mid_c.diff(period)
        df['mom_pos'] = np.sign(df.mom)
        df['mom_slope'] = np.sign(df.mom.diff(1))
        return df

    def add_roc(self, df, period=10):
        df['roc'] = df.mid_c.diff(period)
        return df

    def pivot_points(self, inst, count=2, tf='D'):
        # dfd=self.get_candles(inst, count=count, timeframe=tf)
        dfd = pd.read_pickle(f'./data/{inst}_{tf}.pkl')
        # print(dfd[['mid_o','mid_h','mid_l','mid_c']], '\n')
        YH = dfd.iloc[-2].mid_h
        YL = dfd.iloc[-2].mid_l
        YC = dfd.iloc[-2].mid_c
        # print(f'YH:{YH} YL:{YL} YC:{YC}')

        P = (YH + YL + YC)/3
        R1 = 2*P - YL
        R2 = P + (YH - YL)
        R3 = YH + 2*(P - YL)
        # print(f'P:{P:.5f} R1:{R1:.5f} R2:{R2:.5f} R3:{R3:.5f}')

        S1 = 2*P - YH
        S2 = P - (YH - YL)
        S3 = YL - 2*(YH-P)
        # print(f'P:{P:.5f} S1:{S1:.5f} S2:{S2:.5f} S3:{S3:.5f}')
        pp = dict(
            P=round(P, 5),
            R1=round(R1, 5),
            R2=round(R2, 5),
            R3=round(R3, 5),
            S1=round(S1, 5),
            S2=round(S2, 5),
            S3=round(S3, 5)
        )
        return pp

    def is_trade_allowed_by_pivot(self, inst, price, signal) -> str:
        pp = self.pivot_points(inst)

        if price < pp['S3']:
            msg = f'below S3 : NO SELL HERE!  {price} < {pp["S3"]}'
            if signal == -1:
                print('  **', inst, price, msg, signal)
                return 0
        elif price < pp['S2']:
            msg = f'between S3 and S2: {pp["S3"]} .. {price} .. {pp["S2"]}'
        elif price < pp['S1']:
            msg = f'between S2 and S1 {pp["S2"]} .. {price} .. {pp["S1"]}'
        elif price < pp['P']:
            msg = f'between S1 and Pivot {pp["S1"]} .. {price} .. {pp["P"]}'
        elif price < pp['R1']:
            msg = 'between Pivot and R1'
        elif price < pp['R2']:
            msg = 'between R1 and R2'
        elif price < pp['R3']:
            msg = 'between R2 and R3'
        else:
            msg = f'greater than R3 : NO BUY HERE! {pp["R3"]} < {price}'
            if signal == 1:
                print('  **', inst, price, msg, signal)
                return 0
        # print('  ', inst, msg, signal)
        return signal

    def get_kpi_dict(self, inst, tf: str = 'M5', count: int = 100) -> dict:
        # load ohlc data
        df = pd.read_pickle(f'./data/{inst}_{tf}.pkl')
        # linear regression
        slope, intercept = self.get_linreg(df)
        # momentum
        df = self.add_mom(df)
        # new dict
        kpi_data = dict(
            inst=inst,
            mom_q5=df.mom.quantile(.1).round(5),
            mom_q95=df.mom.quantile(.9).round(5),
            linreg_slope=slope.round(7))

        # add pivots
        pp = self.pivot_points(inst)
        kpi_data = {**kpi_data, **pp}
        return kpi_data

    def load_kpi(self):
        with open("kpi_data.json", "r") as read_file:
            kpi_data = json.load(read_file)
        return kpi_data

    def get_kpi(self, inst, kpi='ALL'):
        kd = self.load_kpi()
        for k in kd:
            if k['inst'] == inst:
                return k[kpi]

    def add_kpi(self, df, inst):
        slope = self.get_kpi(inst, 'linreg_slope')
        mom_q5 = self.get_kpi(inst, 'mom_q5')
        mom_q95 = self.get_kpi(inst, 'mom_q95')
        df['mom_q05'] = mom_q5
        df['mom_q95'] = mom_q95
        df['lr_slope'] = 1 if slope > 0 else -1

    def add_hilo(self, df):
        df['lows'] = np.sign(df.mid_l-df.mid_l.shift(1))
        df['highs'] = np.sign(df.mid_h-df.mid_h.shift(1))
        df['hilo'] = np.where(((df.lows > 0) & (df.highs > 0)), 1, 0)
        df['hilo'] = np.where(((df.lows < 0) & (df.highs < 0)), -1, df['hilo'])

    @staticmethod
    def apply_signal(row):
        c1 = row.hilo > 0
        c2 = row.mom_pos > 0
        c3 = row.mom_slope > 0
        c4 = row.lr_slope > 0

        c5 = row.hilo < 0
        c6 = row.mom_pos < 0
        c7 = row.mom_slope < 0
        c8 = row.lr_slope < 0

        if c1 and c2 and c3 and c4:
            return 1
        elif c5 and c6 and c7 and c8:
            return -1
        else:
            return 0

    def get_signal(self, inst, count=15, tf='M5'):
        df = self.get_candles(inst, count, tf)

        self.add_hilo(df)
        self.add_mom(df)
        self.add_kpi(df, inst)

        # signal conditions
        cd1 = (df.hilo > 0) & (df.mom_pos > 0) & (df.mom_slope > 0) & (df.lr_slope > 0)
        cd2 = (df.hilo < 0) & (df.mom_pos < 0) & (df.mom_slope < 0) & (df.lr_slope < 0)
        df['signal'] = np.where(cd1, 1, 0)
        df['signal'] = np.where(cd2, -1, df['signal'])
        signal1 = df.signal.iloc[-1]

        # Buy condition
        c1 = (df.mom < df.mom_q05) & (df.mom_slope > 0) & (df.mom_slope.shift(1) > 0)
        c2 = (df.mom > df.mom_q95) & (df.mom_slope < 0) & (df.mom_slope.shift(1) < 0)
        df['signal2'] = np.where(c1, 1, 0)
        df['signal2'] = np.where(c2, -1, df['signal2'])
        signal2 = df.signal2.iloc[-1]

        df['signal3'] = df.apply(self.apply_signal, axis=1)

        if signal2 != 0:
            tmp = signal2
        else:
            tmp = signal1

        signal_pivoted = self.is_trade_allowed_by_pivot(
            inst, df.mid_c.iloc[-1], tmp)

        if df.mom.iloc[-1] < df.mom_q05.iloc[-1] or df.mom.iloc[-1] > df.mom_q95.iloc[-1]:
            signaldata = dict(
                inst=inst,
                mom=df.mom.iloc[-1].round(5),
                ql=df.mom_q05.iloc[-1],
                qh=df.mom_q95.iloc[-1],
                signal=signal_pivoted)
            print(f'{signaldata}')
            print(df.iloc[-5:, -8:])

        return signal_pivoted


if __name__ == "__main__":
    print('Testing analyser')
    import v20
    import defs
    ctx = v20.Context(hostname=defs.HOSTNAME, token=defs.key)
    ctx.set_header(key='Authorization', value=defs.key)
    a = Analyser(ctx)
    # print(a.get_kpi_dict('EUR_GBP'))
    # print(a.pivot_points('EUR_GBP', count=2, tf='D'))
    a.get_signal('EUR_USD')
