import pandas as pd
import numpy as np
import json

__version__ = '2022-05-18'


class Quant():
    def __init__(self, cfg) -> None:
        self.cfg = cfg

    def get_candles(self, inst, count=15, tf='M5'):
        params = dict(price='MBA', granularity=tf, count=count)
        candles = self.cfg.ctx.instrument.candles(inst, **params).get('candles')
        return pd.DataFrame.from_dict(Quant.get_rows(candles))

    @ staticmethod
    def get_rows(candles):
        for c in candles:
            c = c.dict()
            row = {}
            row['complete'] = c['complete']
            row['time'] = pd.to_datetime(c['time']).strftime("%Y-%m-%d %H:%M")
            row['volume'] = c['volume']
            for p in ['mid', 'bid', 'ask']:
                for oh in 'ohlc':
                    row[f'{p}_{oh}'] = float(c[p][oh])
            yield(row)

    def fetch_data(self, tf='M5', count=100):
        for inst in self.cfg.get_tradeable_instruments():
            df = self.get_candles(inst, count, tf)
            df.to_pickle(f'./data/{inst}_{tf}.pkl')
        # print('data files updated:', tf, count)

    def update_kpi_file(self):
        kpi_data = []
        for inst in self.cfg.get_tradeable_instruments():
            kpi_data.append(self.get_kpi_dict(inst=inst, tf='M5'))

        with open('kpi_data.json', 'w') as write_file:
            json.dump(kpi_data, write_file, indent=2)

    def get_linreg(self, df):
        x = np.arange(len(df))
        y = list(df.mid_c.values)
        z = np.polyfit(x, y, deg=1)
        slope = z[0]
        intercept = z[1]
        return slope, intercept

    def add_mom(self, df, n=10):
        df['mom'] = df.mid_c.diff(n)
        df['mom_pos'] = np.sign(df.mom)
        df['mom_slope'] = np.sign(df.mom.diff(1))
        return df

    def pivot_points(self, inst, tf='D'):
        dfd = pd.read_pickle(f'./data/{inst}_{tf}.pkl')
        YH = dfd.iloc[-2].mid_h
        YL = dfd.iloc[-2].mid_l
        YC = dfd.iloc[-2].mid_c
        P = (YH + YL + YC)/3
        R1 = 2*P - YL
        R2 = P + (YH - YL)
        R3 = YH + 2*(P - YL)

        S1 = 2*P - YH
        S2 = P - (YH - YL)
        S3 = YL - 2*(YH-P)

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
        return signal

    def get_kpi_dict(self, inst, tf: str = 'M5', count: int = 100) -> dict:
        df = pd.read_pickle(f'./data/{inst}_{tf}.pkl')
        slope, intercept = self.get_linreg(df)
        df = self.add_mom(df)
        kpi_data = dict(
            inst=inst,
            mom_q5=df.mom.quantile(.09).round(5),
            mom_q95=df.mom.quantile(.91).round(5),
            linreg_slope=slope.round(7))

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
        try:
            df['lr_slope'] = 1 if slope > 0 else -1
        except TypeError as te:
            print('exception', te)

    def add_hilo(self, df):
        df['lows'] = np.sign(df.mid_l-df.mid_l.shift(1))
        df['highs'] = np.sign(df.mid_h-df.mid_h.shift(1))
        df['hilo'] = np.where(((df.lows > 0) & (df.highs > 0)), 1, 0)
        df['hilo'] = np.where(((df.lows < 0) & (df.highs < 0)), -1, df['hilo'])

    def add_stochastic(self, df, window=10, roll=3):
        hi = df.mid_h.rolling(window).max()
        lo = df.mid_l.rolling(window).min()
        df['STO_K'] = (df.mid_c - lo)*100/(hi - lo)
        df['STO_D'] = df['STO_K'].rolling(roll).mean()

    def get_stop(self, df, signal):
        # TODO: utolsó 2-3 gyertya alatt vagy max 12 pip
        if signal == 1:
            pass

    def get_extreme_distance(self, df, direction, range=5):
        extreme_distance = None
        if direction == 1:
            extreme_distance = df.ask_c.iloc[-1] - df.bid_l.iloc[-5:].min()
            # print(f'ask_c: {df.ask_c.iloc[-1]} lowest bid:{df.bid_l.iloc[-range:].min()}')
        if direction == -1:
            extreme_distance = df.ask_h.iloc[-5:].max() - df.bid_c.iloc[-1]
            # print(f'ask high: {df.ask_h.iloc[-5:].max()} bid_c:{df.bid_c.iloc[-1]}')
        return extreme_distance

    def get_signal(self, inst: str, count: int = 15, tf: str = 'M5', positioning: int = 0):

        df = self.get_candles(inst, count, tf)
        if df.volume.iloc[-2:].mean() < 100:
            print(f'{inst} low volume: {df.volume.iloc[-2:].mean():.2f}')
            signal = dict(signal=0, signaltype='LV')
            return None

        self.add_hilo(df)
        self.add_mom(df)
        self.add_kpi(df, inst)
        self.add_stochastic(df)

        # Strategy1
        try:
            cd1 = (df.hilo > 0) & (df.mom_pos > 0) & (df.mom_slope > 0) & (df.lr_slope > 0)
            cd2 = (df.hilo < 0) & (df.mom_pos < 0) & (df.mom_slope < 0) & (df.lr_slope < 0)
            df['s1'] = np.where(cd1, 1, 0)
            df['s1'] = np.where(cd2, -1, df['s1'])
            s1 = df.s1.iloc[-1]
        except AttributeError as e:
            print(f'{inst}, {e}')
            return None

        # Strategy2
        c1 = (df.mom < df.mom_q05) & (df.mom_slope > 0) & (df.mom_slope.shift(1) > 0)
        c2 = (df.mom > df.mom_q95) & (df.mom_slope < 0) & (df.mom_slope.shift(1) < 0)
        df['s2'] = np.where(c1, 1, 0)
        df['s2'] = np.where(c2, -1, df['s2'])
        s2 = df.s2.iloc[-1]

        # Strategy3
        cd1 = (df.mom_slope > 0) & (df.lr_slope > 0)
        cd2 = (df.mom_slope < 0) & (df.lr_slope < 0)
        df['s3'] = np.where(cd1, 1, 0)
        df['s3'] = np.where(cd2, -1, df['s3'])
        s3 = df.s3.iloc[-1]

        # Strategy4
        cd1 = (df.hilo > 0) & (df.mom_pos < 0) & (df.mom_slope > 0) & (df.lr_slope > 0)
        cd2 = (df.hilo < 0) & (df.mom_pos > 0) & (df.mom_slope < 0) & (df.lr_slope < 0)
        df['s4'] = np.where(cd1, 1, 0)
        df['s4'] = np.where(cd2, -1, df['s4'])
        s4 = df.s4.iloc[-1]

        signal = dict(
            inst=inst,
            tf=tf,
            count=count,
            signal=s3,
            signaltype='S3',
            lrg=df.lr_slope.iloc[-1],
            low=df.bid_l.iloc[-1],
            high=df.ask_h.iloc[-1],
            stop_level=1,
            stop_dist=1,
            ts_dist=self.get_extreme_distance(df, s3),
            volume=df.volume.iloc[-1]
        )

        return signal


if __name__ == "__main__":
    print('Testing quant')
    Quant().get_signal('AUD_JPY')
