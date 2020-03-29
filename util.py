from threading import Thread
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
