from typing import Any
from dateutil import parser

class LivePrice():
    instrument : str

    def __init__(self, ob: dict[str, Any]):
        self.instrument = ob['instrument']
        self.ask = float(ob['asks'][0]['price'])
        self.bid = float(ob['bids'][0]['price'])
        self.time= parser.parse(ob['time'])

    def get_dict(self):
        return dict(
            instrument=self.instrument,
            ask=self.ask,
            bid=self.bid,
            time=self.time
        )

    def __repr__(self):
        return f"{self.instrument} {self.ask} {self.bid} {self.time}"
