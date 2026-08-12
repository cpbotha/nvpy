# nvPY: cross-platform note-taking app with simplenote syncing
# copyright 2012 by Charl P. Botha <cpbotha@vxlabs.com>
# new BSD license
"""Tk-related helpers that do not import tkinter at module load time."""


class Ucs4NotSupportedError(BaseException):

    def __init__(self, char):
        self.char = char

    def __str__(self):
        return ('non-BMP character {} is not supported in the current Tk version. '
                'The latest Tk will fix this issue. Please consider upgrading to latest OS, Python, and libraries. '
                'Another option is rebuild Python interpreter and libraries with UCS-4 support. '
                'See https://github.com/cpbotha/nvpy/blob/master/docs/ucs-4.rst').format(self.char)


def with_ucs4_error_handling(fn):
    """Catch the non-BMP character error and reraise the Ucs4NotSupportedError."""
    import functools
    import re

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            from tkinter import TclError
            if not isinstance(e, TclError):
                raise
            result = re.match(
                r'character (U\+[0-9a-f]+) is above the range \(U\+0000-U\+FFFF\) allowed by Tcl',
                str(e),
            )
            if result:
                raise Ucs4NotSupportedError(result.group(1)) from e
            raise

    return wrapper


def trace_variable_write(var, callback):
    """Register a write callback on a tkinter variable.

    Tcl 9 removed the legacy ``trace variable`` command used by Variable.trace().
    """
    if hasattr(var, 'trace_add'):
        var.trace_add('write', callback)
    else:
        var.trace('w', callback)
