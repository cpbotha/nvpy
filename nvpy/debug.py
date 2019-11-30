import sys
import functools
import pdb
import threading
import traceback
import logging
import textwrap

lock = threading.Lock()


def format_all_tracebacks():
    output = []
    try:
        for th in threading.enumerate():
            frame = sys._current_frames()[th.ident]
            stack = traceback.format_stack(frame)
            output.append('Thread(ident={}, name={})\n'.format(th.ident, th.name))
            output.extend(stack)
    except Exception as e:
        output.append('\nerror: ' + str(e) + '\n')
    return ''.join(output)


def wrap_buggy_function(fn):
    """ wrap_buggy_function handles any exception and start pdb in interactive mode. """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            with lock:
                # Write debugging information to the log file and stderr.
                msg = textwrap.dedent('''
                    ERROR: An unexpected error occurred.
                    Thread(ident={thread_ident}, name={thread_name})
                    {traceback}
                    Other threads:
                    {all_threads}
                ''').format(
                    thread_ident=threading.current_thread().ident,
                    thread_name=threading.current_thread().name,
                    traceback=traceback.format_exc(),
                    all_threads=format_all_tracebacks(),
                )
                logging.critical(msg)
                sys.stderr.write(msg)

                # Start pdb.
                tb = sys.exc_info()[2]
                pdb.post_mortem(tb)
                raise

    return wrapper
