from abc import abstractmethod

import ccxt

def newExchange(conf):
    ex = conf['exchange']
    if ex.lower() == 'deribit':
        return Deribit(conf)
    elif ex.lower() == 'bitmex':
        return Bitmex(conf)

class Exchange:
    name = 'generic_exchange'

    def __init__(self, conf, ccxt_ex_class, market="BTC/USD"):
        self.conf = conf
        self.ccxt = ccxt_ex_class(self.conf['ccxt'])
        self.markets = self.ccxt.load_markets()
        self.market = market
        self.ticker = None
        pass

    def fetchTicker(self, market=None):
        if not market:
            market = self.market
        self.ticker = self.ccxt.fetch_ticker(market)

    @abstractmethod
    def getOI(self):
        pass

    @abstractmethod
    def getPrice(self):
        pass

class Bitmex(Exchange):
    name = 'Bitmex'

    def __init__(self, conf):
        Exchange.__init__(self, conf, ccxt.bitmex, market=conf.get("market", "BTC/USD"))

    def getOI(self):
        return self.ticker["info"]["openInterest"]

    def getPrice(self):
        return self.ticker["info"]["midPrice"]

class Deribit(Exchange):
    name = 'Deribit'

    def __init__(self, conf):
        Exchange.__init__(self, conf, ccxt.deribit, market=conf.get("market", "BTC-PERPETUAL"))

    def getOI(self):
        return self.ticker["info"]["open_interest"]

    def getPrice(self):
        return (self.ticker["info"]["best_ask_price"] + self.ticker["info"]["best_bid_price"]) / 2
