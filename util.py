from threading import Thread, Event, Lock
from functools import wraps

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

class timer:
    def __init__(self, duration):
        self.duration = duration
        self.running = False
        self.cancel = Event()
        self.lock = Lock()

    def start(self):
        with self.lock:
            if self.running:
                self.cancel.set()
            self.running = True
        self.cooldown()

    @detach
    def cooldown(self):
        self.cancel.wait(self.duration)
        with self.lock:
            if self.cancel.is_set():
                self.cancel.clear()
                return
            self.running = False
