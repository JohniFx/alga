import v20
import defs

class TradeUnitCalculator():

    def __init__(self, ctx, pairs_list) -> None:
        self.ctx = ctx
        self.pairs_list = pairs_list
        instruments_raw = ctx.account.instruments.list()
        self.marginrates = {x['name'] : float(x['marginRate']) for x in instruments_raw['instruments']}
        self.prices = ctx.prices.get(pairs_list)

    def get_margin_for_units(self, units, inst) -> float:
        marginRate = self.marginRates[inst]
        price = self.prices[inst]

        trade_margin = price.mid * marginRate * price.mid_conv * units
        return trade_margin

    def get_units_for_margin(self, margin, inst) -> int:
        marginRate = self.marginRates[inst]
        price = self.prices[inst]

        units = margin / (price.mid * marginRate * price.mid_conv)
        return int(units)

if __name__ == "__main__":
    ctx = v20.Context(hostname=defs.HOSTNAME, token=defs.key)
    ctx.set_header(key='Authorization', value=defs.key)
    # test it here ... 
