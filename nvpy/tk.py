# nvPY: cross-platform note-taking app with simplenote syncing
# copyright 2012 by Charl P. Botha <cpbotha@vxlabs.com>
# new BSD license

# Tkinter and ttk documentation recommend pulling all symbols into client
# module namespace. I don't like that, so first pulling into this module
# tk, then can use tk.whatever in main module.

from tkinter import *
from tkinter.ttk import *  # type:ignore


class Ucs4NotSupportedError(BaseException):
    def __init__(self, char):
        self.char = char

    def __str__(self):
        return ('non-BMP character {} is not supported.  '
                'Please rebuild python interpreter and libraries with UCS-4 support.  '
                'See https://github.com/cpbotha/nvpy/blob/master/docs/ucs-4.rst').format(self.char)


def with_ucs4_error_handling(fn):
    """ Catch the non-BMP character error and reraise the Ucs4NotSupportedError. """
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except TclError as e:
            import re
            result = re.match(r'character (U\+[0-9a-f]+) is above the range \(U\+0000-U\+FFFF\) allowed by Tcl', str(e))
            if result:
                char = result.group(1)
                raise Ucs4NotSupportedError(char)
            raise

    return wrapper


########################################################################
# Apply the monkey patches for convert TclError to Ucs4NotSupportedError

_Text = Text
del Text


class Text(_Text):  # type:ignore
    @with_ucs4_error_handling
    def insert(self, *args, **kwargs):
        return _Text.insert(self, *args, **kwargs)
