import asyncio
import logging
import math
import os
import signal
import sys
import time

from exchange import newExchange
from oidelta import OIDeltas
from telegram import Telegram
from util import unbuffered, pprint, priceRange, coloredValue
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

try:
    telegram = Telegram(conf["telegram"])
except Exception as err:
    print(err)

def bye(a, b):
    print("\nbye")
    os._exit(0)

async def main():
    signal.signal(signal.SIGINT, bye)
    signal.signal(signal.SIGTERM, bye)


    global conf
    settings = S()

    # init ccxt exchange
    exchange = newExchange(conf)
    conf["market"] = exchange.market

    pprint("tracking OI levels for {}:{}".format(exchange.name, exchange.market))

    await exchange.fetchTicker()
    oi0 = exchange.getOI()
    time.sleep(S.interval)
    pRef = exchange.getPrice()
    pmin = pRef
    pmin1 = pRef
    pmax = pRef
    pmax1 = pRef

    # will track global delta on custom duration (S.alertInterval)
    oiAlerts = OIDeltas(0, settings, S.alertInterval)
    oiAlertT0 = time.time()
    pAlert = pRef
    oiAlertCircles = ""

    # main data dicts mapping a price range with an OIDelta
    total = {}    # stores OIDeltas for the whole program runtime
    session = {}  # partial OIDeltas, works in the same way as total, but is reset every profileTicks
    i = 0
    while True:
        try:
            # fetch ticker data & calculate delta oi (oi - previousOI)
            await exchange.fetchTicker()
            oi = exchange.getOI()
            delta = oi - oi0
            oi0 = oi

            # get ticker price, store min/max for session, and calculate price range p
            pReal = exchange.getPrice()
            pmin = min(pmin, pReal)
            pmin1 = min(pmin1, pReal)
            pmax = max(pmax, pReal)
            pmax1 = max(pmax1, pReal)
            p = priceRange(pReal)
            # if p != p0:
            #     print()
            p0 = p

            # check that OIDelta exists for current price range in our data dicts, if not create them
            if not p in total:
                total[p] = OIDeltas(p, settings, settings.d1, settings.d2, 0)
            if not p in session:
                session[p] = OIDeltas(p, settings, settings.d1, settings.d2, 0)

            # retreive OIDeltas object for the current price range, for both dicts
            oidTotal = total[p]
            oidSession = session[p]
            # add current delta
            tasks = [
                asyncio.create_task(oidTotal.add(delta)),
                asyncio.create_task(oidSession.add(delta)),
                asyncio.create_task(oiAlerts.add(delta)),
            ]
            await asyncio.gather(*tasks)
            # print current level
            pprint("{}        OI: {:>16,.0f}".format(oidTotal, oi))

            # increment main tick
            i+=1

            # check if we reached alert threshold
            f = oiAlerts.frames[S.alertInterval]
            if math.fabs(f.value) >= S.alertThreshold:
                # circles mic-mac
                blue_diamond = "🔹"
                orange_diamond = "🔸"
                if f.value > 0:
                    if orange_diamond in oiAlertCircles:
                        oiAlertCircles = ""
                    oiAlertCircles += blue_diamond
                else:
                    if blue_diamond in oiAlertCircles:
                        oiAlertCircles = ""
                    oiAlertCircles += orange_diamond

                alertsDuration = time.time() - oiAlertT0
                alertsDuration = min(alertsDuration, S.alertInterval)
                msg = "*{}:{}* - {:.1f} (*{:+,.1f}*)\noi: {:+,.0f} in {:.0f}s {}\nmin/max: {:.1f}/{:.1f} ({:.1f})".format(
                    conf["exchange"],
                    conf["market"],
                    pReal,
                    pReal - pAlert,
                    f.value,
                    alertsDuration,
                    oiAlertCircles,
                    pmin, pmax,
                    pmax - pmin,
                )
                pprint("alert reached")
                print(msg + "\n")
                if alertsDuration <= S.alertInterval:
                        try:
                            telegram.sendMessage(msg)
                        except Exception as err:
                            pprint(err)
                # reset alert data
                await oiAlerts.cancel()
                oiAlertT0 = time.time()
                f.value = 0
                pAlert, pRef, pmax, pmin = pReal, pReal, pReal, pReal


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
                    coloredValue(totalDelta, S.interval * S.profileTicks, threshold=S.threshold),
                ))
                # reset current profile summary session
                session = {}
                pRef, pmax, pmin = pReal, pReal, pReal
        except:
            logging.exception("unhandled exception")
        await asyncio.sleep(S.interval)

if __name__ == '__main__':
    asyncio.run(main())
