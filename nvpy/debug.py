import sys
import functools
import pdb
import threading

lock = threading.Lock()


def wrap_buggy_function(fn):
    """ wrap_buggy_function handles any exception and start pdb in interactive mode. """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            with lock:
                tb = sys.exc_info()[2]
                pdb.post_mortem(tb)
                raise

    return wrapper

