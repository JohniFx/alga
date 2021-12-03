class TradingOrder():

    def __init__(self, instrument, initprice) -> None:
        self.instrument = instrument
        self.initprice = initprice
        self.price_prev = initprice

    def on_tick(self, price, direction, dist=0):
        if direction == 1:
            if price > (self.price_prev+dist):
                self.move_stop()

        if direction == -1:
            if price < (self.price_prev - dist):
                self.move_stop()
        self.price_prev = price

    def move_stop(self):
        pass
