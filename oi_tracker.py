import logging
import math
import os
import signal
import sys
import time
import datetime
import requests

from colorama import Fore, Style
from threading import Lock

from exchange import newExchange
from util import detach, unbuffered, timer
from envparse import env, ConfigurationError

# parse environment
if __name__ == "__main__":
	import argparse

	parser = argparse.ArgumentParser()
	parser.add_argument("-e", "--env", type=str, default="env",
						help="environment file, contains config, exchange, keys etc.")
	parser.add_argument("-nc", "--nocolor", action='store_true', default=False, help="disable colored tty")
	args = parser.parse_args()
	if not os.path.isfile(args.env):
		print("no environment file (looking for \"%s\")" % args.env)
	else:
		env.read_envfile(args.env)
	if not sys.stdout.isatty():
		sys.stdout = unbuffered(sys.stdout)

# settings
class S:
	interval        = float(env('interval', 5.))         # ticker interval
	threshold       = float(env('threshold', 5000.))     # deltaOI/sec threshold before highlighting (red/green)
	d1              = float(env('d1', 30))               # d1 period in secs
	d2              = float(env('d2', 150))              # d2 period in secs
	pRange          = float(env('pRange', 10))           # price range size
	profileTicks    = float(env('profileTicks', 180.))   # display oi profile every number of ticks (so 180*5s == every 15minutee)

	# telegram alert settings
	alertInterval   = float(env('alertInterval', 300))   # lookback last alertInterval seconds for telegram notification
	alertThreshold  = float(env('alertThreshold', 5e6))  # absolute OI-delta value above which a notification should be sent
	alertCooldown   = float(env('alertCooldown', 60))    # alert cooldown in seconds

# exchange and other meta-config
try:
	conf = {
		'telegram': {
			'disabled': bool(env('TELEGRAM_DISABLED', False)),
			'bot': env("TELEGRAM_TOKEN", ""),
			'chat': env("TELEGRAM_CHAT", ""),
		},
		'exchange': env("EXCHANGE"),
		'market': env("MARKET", None),
		'ccxt': {
			'apiKey': env("API_KEY"),
			'secret': env("API_SEC"),
			'enableRateLimit': True,
		},
	}
	if not conf["market"]:
		del(conf["market"])
except ConfigurationError as err:
	print(err)
	exit(1)

# setup telegram
telegramPrefix = \
	"https://api.telegram.org/bot{token}/{{method}}?chat_id={chatID}".format(
		token=conf["telegram"]["bot"],
		chatID=conf["telegram"]["chat"],
	)
telegramMsgFormat = telegramPrefix.format(method="sendMessage") + "&parse_mode=Markdown&text={}"
telegramGetMyCmds = telegramPrefix.format(method="getMyCommands")
if not conf["telegram"]["disabled"]:
	# check that telegram is working
	try:
		resp = requests.get(telegramGetMyCmds)
		respJson = resp.json()
		if not "ok" in respJson or not respJson["ok"]:
			raise Exception(repr(respJson))
	except Exception as err:
		print("couldn't init telegram: %s" % err)
		print("disabling telegram alert")
		conf["telegram"]["disabled"] = True

# init ccxt exchange
exchange = newExchange(conf)
conf["market"] = exchange.market

# OIDeltas tracks OI evolution between each data, on several configurable timeframes (d1, d2 and total/lifetime)
class OIDeltas:
	d1 = S.d1
	d1Delta = 0

	d2 = S.d2
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
		time.sleep(self.d1)
		with self.lock:
			self.d1Delta -= q

	@detach
	def removeD2(self, q):
		time.sleep(self.d2)
		with self.lock:
			self.d2Delta -= q

	# how to display data
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
			s += "total: {}  ".format(coloredValue(self.totalDelta, self.ticks*S.interval))
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

# used to color price with above colors to differentiate between price levels
def coloredPrice(p, step=S.pRange):
	s = "{:>7,.0f}".format(p)
	if args.nocolor:
		return s
	else:
		return "{}{}{}".format(priceColors[int((p / step) % len(priceColors))], s, Style.RESET_ALL)


def coloredValue(v, duration=1, threshold=S.threshold, padSize=12, decimals=0, plus=False):
	s = '{:{prefix}{pad},.{decimals}f}'.format(v, prefix="+" if plus else ">", pad=padSize, decimals=decimals)
	if args.nocolor:
		return s
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
	print("\nbye")
	os._exit(0)

if __name__ == "__main__":
	signal.signal(signal.SIGINT, bye)
	signal.signal(signal.SIGTERM, bye)

	pprint("tracking OI levels for {}:{}".format(exchange.name, exchange.market))

	exchange.fetchTicker()
	oi0 = exchange.getOI()
	time.sleep(S.interval)
	pRef = exchange.getPrice()
	p0 = priceRange(pRef)
	pmin = pRef
	pmax = pRef

	# will track global delta on custom duration (S.alertInterval)
	oiAlerts = OIDeltas(0)
	oiAlerts.d1 = S.alertInterval
	oiAlerts.d2 = 0 # d2 interval not used for now for alerts
	oiCooldown = timer(S.alertCooldown)

	# main data dicts mapping a price range with an OIDelta
	total = {}    # stores OIDeltas for the whole program runtime
	session = {}  # partial OIDeltas, works in the same way as total, but is reset every profileTicks
	i = 0
	while True:
		try:
			# fetch ticker data & calculate delta oi (oi - previousOI)
			exchange.fetchTicker()
			oi = exchange.getOI()
			delta = oi - oi0
			oi0 = oi

			# get ticker price, store min/max for session, and calculate price range p
			pReal = exchange.getPrice()
			pmin = min(pmin, pReal)
			pmax = max(pmax, pReal)
			p = priceRange(pReal)
			# if p != p0:
			# 	print()
			p0 = p

			# check that OIDelta exists for current price range in our data dicts, if not create them
			if not p in total:
				total[p] = OIDeltas(p)
			if not p in session:
				session[p] = OIDeltas(p)

			# retreive OIDeltas object for the current price range, for both dicts
			oidTotal = total[p]
			oidSession = session[p]
			# add current delta
			oidTotal.add(delta)
			oidSession.add(delta)
			oiAlerts.add(delta)
			# print current level
			pprint("{}        OI: {:>16,.0f}".format(oidTotal, oi))

			# increment main tick
			i+=1

			# check if we reached alert threshold
			if math.fabs(oiAlerts.d1Delta) >= S.alertThreshold:
				if oiCooldown.running:
					pass
					# print()
					# pprint("cooling down: %.0f\n" % oiAlerts.d1Delta)
				else:
					oiCooldown.start()
					msg = "{}:{} drunk emirati: {:+.0f} in last {:.0f} minutes. Ticker: {:.1f}".format(
						conf["exchange"],
						conf["market"],
						oiAlerts.d1Delta,
						(S.alertInterval / 60),
						pReal
					)
					print()
					pprint(msg + "\n")
					if not conf["telegram"]["disabled"]:
						try:
							resp = requests.get(telegramMsgFormat.format(msg))
							if not resp.json()["ok"]:
								raise Exception(repr(resp.json()))
						except Exception as err:
							pprint("telegram api call error: %s" % err)

			# check if current profile session is elapsed or not
			if i % S.profileTicks == 0:
				# current session is elapsed, S.profileTicks reached, so we print profile summary
				print()
				pprint("profile for %s:%s, last %d minutes:" % (
					exchange.name,
					exchange.market,
					(S.interval * S.profileTicks) / 60,
				))
				totalDelta = 0
				for p, oid in sorted(session.items(), reverse=True):
					print("  {}".format(oid.repr(last=False, d1=False, d2=False)))
					totalDelta += oid.totalDelta
				print("\n    ticker: {} ({})  min/max: {:.1f}/{:.1f} (<> {})  oi: {}\n".format(
					pReal,
					coloredValue(pReal-pRef, 1, threshold=50, padSize=4, decimals=1, plus=True),
					pmin,
					pmax,
					coloredValue(pmax-pmin, 1, threshold=100, padSize=4, decimals=1),
					coloredValue(totalDelta, S.interval * S.profileTicks),
				))
				# reset current profile summary session
				session = {}
				pRef, pmax, pmin = pReal, pReal, pReal
		except:
			logging.exception("unhandled exception")
		time.sleep(S.interval)
