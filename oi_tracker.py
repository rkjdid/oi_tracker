import logging
import time
import datetime
import ccxt

from colorama import Fore, Style
from threading import Lock
from sync import detach
from envparse import env

env.read_envfile("env")
exchange = ccxt.bitmex({
    'apiKey': env("API_KEY"),
    'secret': env("API_SEC"),
    'enableRateLimit': True,
})

markets = exchange.load_markets()

interval = 5      # measure OI
threshold = 5000  # deltaOI/sec threshold before highlighting (red/green)
d1 = 30
d2 = 150
pRange = 10        # price range size

class OIDeltas:
	d1Delta = 0
	d2Delta = 0
	totalDelta = 0
	lock = Lock()
	last = 0

	def __init__(self, p):
		self.price = p

	def add(self, delta):
		self.last = delta
		with self.lock:
			self.d1Delta += delta
			self.removeD1(delta)
			self.d2Delta += delta
			self.removeD2(delta)
			self.totalDelta += delta

	@detach
	def removeD1(self, q):
		time.sleep(d1)
		with self.lock:
			self.d1Delta -= q

	@detach
	def removeD2(self, q):
		time.sleep(d2)
		with self.lock:
			self.d2Delta -= q

	def __repr__(self):
		return "  {}   last: {}    {}s: {}    {}s: {}    total: {}".format(
			coloredPrice(self.price),
			coloredValue(self.last, 5),
			d1, coloredValue(self.d1Delta, d1),
			d2, coloredValue(self.d2Delta, d2),
			coloredValue(self.totalDelta, d2*2),
		)

def priceRange(p, step=10):
	return p - p % step

priceColors = [
	Fore.LIGHTWHITE_EX,
	Fore.LIGHTRED_EX,
	Fore.LIGHTBLUE_EX,
	Fore.LIGHTGREEN_EX,
]

def coloredPrice(p, step=pRange):
	return "{}{:>7,.0f}{}".format(priceColors[int((p / step) % len(priceColors))], p, Style.RESET_ALL)

def coloredValue(v, duration, thr=threshold, padSize=12):
	s = '{:>{pad},.0f}'.format(v, pad=padSize)
	perSec = v / duration
	if perSec > thr:
		s = Fore.GREEN + s + Style.RESET_ALL
	elif perSec < -thr:
		s = Fore.RED + s + Style.RESET_ALL
	return s

def pprint(msg, *mods):
	pre = ""
	for mod in mods:
		pre += mod
	print("{} {}{}{}".format(
		datetime.datetime.now().strftime("%m-%d %H:%M:%S"),
		pre,
		msg,
		Style.RESET_ALL,
	))

if __name__ == "__main__":
	oiPerPrice = {}

	ti = exchange.fetch_ticker('BTC/USD')['info']
	oi0 = ti['openInterest']
	time.sleep(interval)

	while True:
		try:
			ti = exchange.fetch_ticker('BTC/USD')['info']
			oi = ti['openInterest']
			delta = oi - oi0
			oi0 = oi
			p = priceRange(ti['midPrice'])
			if not p in oiPerPrice:
				oiPerPrice[p] = OIDeltas(p)
			oiDelta = oiPerPrice[p]
			oiDelta.add(delta)
			pprint("{}        OI: {:>16,.0f}".format(oiDelta, oi))
		except:
			logging.exception("unhandled exception")
		time.sleep(interval)
