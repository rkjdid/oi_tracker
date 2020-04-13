import asyncio
from asyncio import CancelledError

from util import coloredPrice, coloredValue

# OIDeltas tracks OI evolution between each data, on several configurable timeframes (d1, d2 and total/lifetime)
class OIDeltas:
    class Frame:
        def __init__(self, delay):
            self.delay = delay
            self.value = 0
            self.tasks = []
            self.lock = asyncio.Lock()

        async def add(self, delta):
            async with self.lock:
                self.value += delta
                if self.delay <= 0:
                    return

                # will remove delta after delay
                t = asyncio.create_task(self.remove(delta, self.delay))
                self.tasks.append(t)

                # will clear remove task when done
                asyncio.create_task(self.clearAfter(t))

        async def clearAfter(self, task):
            # wait on remove task, to clear it from self.tasks
            try:
                await task
            except CancelledError:
                pass
            finally:
                async with self.lock:
                    self.tasks.remove(task)

        async def remove(self, delta, delay):
            await asyncio.sleep(delay)
            async with self.lock:
                self.value -= delta

        async def cancel(self):
            async with self.lock:
                for t in self.tasks:
                    t.cancel()

    def __init__(self, p, settings, *delays):
        self.last = 0
        self.ticks = 0
        self.frames = {}
        self.price = p
        for d in delays:
            d = 0 if d < 0 else d
            self.frames[d] = OIDeltas.Frame(d)
        self.threshold = settings.threshold
        self.interval = settings.interval

    async def add(self, delta):
        self.last = delta
        self.ticks += 1
        tasks = []
        for _, f in self.frames.items():
            tasks.append(asyncio.create_task(f.add(delta)))
        await asyncio.gather(*tasks)

    async def cancel(self):
        t = []
        for _, f in self.frames.items():
            t.append(asyncio.create_task(f.cancel()))
        await asyncio.gather(*t)

    # how to display data
    def repr(self, price=True, last=True, ticks=True, ignore=()):
        s = ""
        if price:
            s += coloredPrice(self.price) + "  "
        if last:
            s += "last: {}  ".format(coloredValue(self.last, self.interval))
        for _, f in self.frames.items():
            if f.delay in ignore:
                continue
            if f.delay > 0:
                s += "{}s: {}  ".format(f.delay, coloredValue(f.value, f.delay))
            else:
                s += "total: {}  ".format(coloredValue(f.value, nocolor=True))
        if ticks:
            s += "ticks: {:>4}  ".format(self.ticks)
        return s.strip()

    def __repr__(self):
        return self.repr()
