import argparse
import logging
import os
import signal
import time
import datetime

from colorama import Fore, Style
from threading import Lock

from exchange import newExchange
from sync import detach
from envparse import env

# parse environment
if __name__ == "__main__":
	import argparse

	parser = argparse.ArgumentParser()
	parser.add_argument("-e", "--env", type=str, default="env",
						help="environment file, contains config, exchange, keys etc.")
	args = parser.parse_args()
	if not os.path.isfile(args.env):
		print("no environment file" % args.env)
	else:
		env.read_envfile(args.env)

# prepare exchange configuration from env
conf = {
	'exchange': env("EXCHANGE"),
	'market': env("MARKET", None),
	'apiKey': env("API_KEY"),
	'secret': env("API_SEC"),
	'enableRateLimit': True,
}
if not conf["market"]:
	del(conf["market"])

# init ccxt exchange
exchange = newExchange(conf)

# main settings
class S:
	interval =  env('interval', 5.)      # measure OI
	threshold = env('threshold', 5000.)  # deltaOI/sec threshold before highlighting (red/green)
	d1 =        env('d1', 30)            # d1 period in secs
	d2 =        env('d2', 150)           # d2 period in secs
	pRange =    env('pRange', 10)        # price range size

class OIDeltas:
	d1Delta = 0
	d2Delta = 0
	totalDelta = 0
	lock = Lock()
	last = 0
	ticks = 0

	def __init__(self, p):
		self.price = p

	def add(self, delta):
		self.last = delta
		self.ticks += 1
		with self.lock:
			self.d1Delta += delta
			self.removeD1(delta)
			self.d2Delta += delta
			self.removeD2(delta)
			self.totalDelta += delta

	@detach
	def removeD1(self, q):
		time.sleep(S.d1)
		with self.lock:
			self.d1Delta -= q

	@detach
	def removeD2(self, q):
		time.sleep(S.d2)
		with self.lock:
			self.d2Delta -= q

	def repr(self, price=True, last=True, d1=True, d2=True, total=True, ticks=True, avg=True):
		s = ""
		if price:
			s += coloredPrice(self.price) + "  "
		if last:
			s += "last: {}  ".format(coloredValue(self.last, S.interval))
		if d1:
			s += "{}s: {}  ".format(S.d1, coloredValue(self.d1Delta, S.d1))
		if d2:
			s += "{}s: {}  ".format(S.d2, coloredValue(self.d2Delta, S.d2))
		if total:
			s += "total: {}  ".format(coloredValue(self.totalDelta, S.d2 * 2))
		if ticks:
			s += "ticks: {:>4}  ".format(self.ticks)
		if avg:
			ticks = self.ticks if self.ticks > 0 else 1
			s += "avg: {}  ".format(coloredValue(self.totalDelta / ticks, S.interval, threshold=S.threshold / 2))
		return s.strip()

	def __repr__(self):
		return self.repr()

def priceRange(p, step=10):
	return p - p % step

priceColors = [
	Fore.LIGHTWHITE_EX,
	Fore.LIGHTRED_EX,
	Fore.LIGHTBLUE_EX,
	Fore.LIGHTGREEN_EX,
	Fore.LIGHTMAGENTA_EX,
	Fore.LIGHTCYAN_EX,
	Fore.LIGHTBLACK_EX,
]

def coloredPrice(p, step=S.pRange):
	return "{}{:>7,.0f}{}".format(priceColors[int((p / step) % len(priceColors))], p, Style.RESET_ALL)

def coloredValue(v, duration, threshold=S.threshold, padSize=12):
	s = '{:>{pad},.0f}'.format(v, pad=padSize)
	perSec = v / duration
	if perSec >= threshold:
		s = Fore.GREEN + s + Style.RESET_ALL
	elif perSec <= -threshold:
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

def bye(a, b):
	print("bye")
	os._exit(0)

if __name__ == "__main__":
	exchange.fetchTicker()
	oi0 = exchange.getOI()
	time.sleep(S.interval)
	p0 = priceRange(exchange.getPrice())

	signal.signal(signal.SIGINT, bye)
	signal.signal(signal.SIGTERM, bye)

	oiPerPrice = {}
	while True:
		try:
			exchange.fetchTicker()
			oi = exchange.getOI()
			delta = oi - oi0
			oi0 = oi
			p = priceRange(exchange.getPrice())
			if p != p0:
				print()
			p0 = p
			if not p in oiPerPrice:
				oiPerPrice[p] = OIDeltas(p)
			oiDelta = oiPerPrice[p]
			oiDelta.add(delta)
			pprint("{}        OI: {:>16,.0f}".format(oiDelta, oi))
		except:
			logging.exception("unhandled exception")
		time.sleep(S.interval)
