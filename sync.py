from threading import Thread
from functools import wraps

def detach(target):
    @wraps(target)
    def detach_func(*args, **kwargs):
        runner = Thread(target=target, args=args, kwargs=kwargs)
        runner.start()
        return runner

    return detach_func
