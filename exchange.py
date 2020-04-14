import asyncio
import logging
from abc import abstractmethod

import ccxtpro as ccxt
from util import pprint


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
        self.market = market
        self.ticker = None
        self.oi = None
        self.trades = []
        self.tradesLock = asyncio.Lock()
        self.liquidationLock = asyncio.Lock()

    def __repr__(self):
        return "{}:{}".format(self.name, self.market)

    async def fetchTicker(self, market=None):
        if not market:
            market = self.market
        self.ticker = await self.ccxt.fetch_ticker(market)
        return self.ticker

    async def watchTicker(self, newOI: asyncio.Event):
        while True:
            try:
                if "watchTicker" in self.ccxt.has:
                    self.ticker = await self.ccxt.watch_ticker(self.market)
                else:
                    await asyncio.sleep(2)
                    await self.fetchTicker()
            except ccxt.base.errors.ExchangeNotAvailable as err:
                pprint("%s: %s" % (self, err))
            except:
                logging.exception("watchTicker unhandled exception")
            oi = self.getOI()
            if oi != self.oi:
                self.oi = oi
                newOI.set()

    async def watchTrades(self):
        while True:
            trade = await self.ccxt.watchTrades(self.market)
            with self.tradesLock:
                self.trades.append(trade)

    async def watchLiquidations(self, market=None):
        raise NotImplemented()

    def computeTrades(self):
        deltaVolume = 0
        with self.tradesLock:
            for t in self.trades:
                if t["type"].lower() == "sell":
                    v = -v
                deltaVolume += v
            self.trades = []
        return deltaVolume

    async def computeLiquidations(self):
        deltaLiquidations = 0

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

    def watchLiquidations(self, market=None):
        if not market:
            market = self.market
        return self.ccxt.watch_liquidations(market)

class Deribit(Exchange):
    name = 'Deribit'

    def __init__(self, conf):
        Exchange.__init__(self, conf, ccxt.deribit, market=conf.get("market", "BTC-PERPETUAL"))

    def getOI(self):
        return self.ticker["info"]["open_interest"]

    def getPrice(self):
        return (self.ticker["info"]["best_ask_price"] + self.ticker["info"]["best_bid_price"]) / 2
