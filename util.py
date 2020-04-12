import datetime
from threading import Thread
from functools import wraps

from colorama import Fore, Style

def detach(target):
    @wraps(target)
    def detach_func(*args, **kwargs):
        runner = Thread(target=target, args=args, kwargs=kwargs)
        runner.start()
        return runner

    return detach_func

# to use on stdouf if needs be (|tee -a)
# https://stackoverflow.com/a/107717
class unbuffered(object):
    def __init__(self, stream):
        self.stream = stream

    def write(self, data):
        self.stream.write(data)
        self.stream.flush()

    def writelines(self, datas):
        self.stream.writelines(datas)
        self.stream.flush()

    def __getattr__(self, attr):
        return getattr(self.stream, attr)

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
def coloredPrice(p, step=10, nocolor=False):
    s = "{:>7,.0f}".format(p)
    if nocolor:
        return s
    else:
        return "{}{}{}".format(priceColors[int((p / step) % len(priceColors))], s, Style.RESET_ALL)


def coloredValue(v, duration=1, threshold=5000, padSize=12, decimals=0, plus=False, nocolor=False):
    s = '{:{prefix}{pad},.{decimals}f}'.format(v, prefix="+" if plus else ">", pad=padSize, decimals=decimals)
    if nocolor:
        return s
    perSec = v / duration
    if perSec >= threshold:
        s = Fore.GREEN + s + Style.RESET_ALL
    elif perSec <= -threshold:
        s = Fore.RED + s + Style.RESET_ALL
    return s


def pprint(*msg):
    print(datetime.datetime.now().strftime("%m-%d %H:%M:%S"),
        *msg,
        Style.RESET_ALL,
    )
