import cfg
import numpy as np
import pandas as pd
import json, pickle

__version__ = '2022-01-24'

class Quant():
    def __init__(self) -> None:
        pass
    
    def get_candles(self, inst, count=15, timeframe='M5'):
        params = dict(
            price='MBA',
            granularity=timeframe,
            count=count)

        candles = cfg.ctx.instrument.candles(inst, **params).get('candles')

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

    #TODO:  átrakni cfg-be
    def fetch_data(self, tf='M5', count=100):
        for inst in cfg.tradeable_instruments:
            df = self.get_candles(inst, count, tf)
            df.to_pickle(f'./data/{inst}_{tf}.pkl')
        print('data files have been updated')

    def update_kpi_file(self):
        kpi_data=[]
        for inst in cfg.tradeable_instruments:
            kpi_data.append(self.get_kpi_dict(inst=inst, tf='M5'))
        with open('kpi_data.json', 'w') as write_file:
            json.dump(kpi_data, write_file, indent=2)
        print('kpi data has been updated')

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
        df['lr_slope'] = 1 if slope > 0 else -1

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
        if signal == 1:
            pass

    def get_signal(self, inst, count=15, tf='M5'):
        print(f'get signal: {inst} {count} {tf}')
        df = self.get_candles(inst, count, tf)
        self.add_hilo(df)
        self.add_mom(df)
        self.add_kpi(df, inst)
        self.add_stochastic(df, 10, 3)

        # Strategy1
        cd1 = (df.hilo > 0) & (df.mom_pos > 0) & (
            df.mom_slope > 0) & (df.lr_slope > 0)
        cd2 = (df.hilo < 0) & (df.mom_pos < 0) & (
            df.mom_slope < 0) & (df.lr_slope < 0)
        df['signal'] = np.where(cd1, 1, 0)
        df['signal'] = np.where(cd2, -1, df['signal'])
        s1 = df.signal.iloc[-1]

        # Strategy2
        c1 = (df.mom < df.mom_q05) & (
            df.mom_slope > 0) & (df.mom_slope.shift(1) > 0)
        c2 = (df.mom > df.mom_q95) & (
            df.mom_slope < 0) & (df.mom_slope.shift(1) < 0)
        df['signal2'] = np.where(c1, 1, 0)
        df['signal2'] = np.where(c2, -1, df['signal2'])
        s2 = df.signal2.iloc[-1]

        # Strategy3
        sc1 = (df.STO_K > 86) & (df.lr_slope > 0)
        sc2 = (df.STO_K < 14) & (df.lr_slope < 0)
        df['signal_stoch'] = np.where(sc1, -1, 0)
        df['signal_stoch'] = np.where(sc2, 1, df['signal_stoch'])
        s3 = df.signal_stoch.iloc[-1]

        # Strategy4
        cd1 = (df.hilo > 0) & (df.mom_pos < 0) & (
            df.mom_slope > 0) & (df.lr_slope > 0)
        cd2 = (df.hilo < 0) & (df.mom_pos > 0) & (
            df.mom_slope < 0) & (df.lr_slope < 0)
        df['s4'] = np.where(cd1, 1, 0)
        df['s4'] = np.where(cd2, -1, df['s4'])
        s4 = 0

        signals = dict(
            inst=inst,
            s1=s1,
            s2=s2,
            s3=s3,
            s4=s4,
            lrg=df.lr_slope.iloc[-1],
            sto=df.STO_K.iloc[-1].round(2)
        )

        print(signals)
        if (s1 == s2) and (s2 == s3) and (s3 == df.lr_slope.iloc[-1]):
            print('** supersignal **')
            return s1, 'XL'

        if s3 != 0:
            return s3, 'S3'
        if s2 != 0:
            return s2, 'S2'
        if s4 != 0:
            return s4, 'S4'
        if s1 != 0:
            return s1, 'S1'

        return 0, ''


if __name__ == "__main__":
    import sys, os
    print('Testing quant')
    try:
        a = Quant()
        a.get_signal('AUD_JPY')
        for m in cfg.messages:
            print(m)
    except KeyboardInterrupt:
        sys.exit(1)
        thread.interrupt_main()
        os._exit(1)
    finally:        
        os._exit(1)


