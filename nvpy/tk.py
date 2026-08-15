# nvPY: cross-platform note-taking app with simplenote syncing
# copyright 2012 by Charl P. Botha <cpbotha@vxlabs.com>
# new BSD license
""" Tkinter and ttk wrappers and monkey patcher

Tkinter and ttk documentation recommend pulling all symbols into client
module namespace. I don't like that, so first pulling into this module
tk, then can use tk.whatever in main module.

This module also applies a monkey patch for UCS4 error handling.
"""

import platform
import sys


def _tkinter_missing_error(exc: ImportError) -> ImportError:
    ver = f'{sys.version_info.major}.{sys.version_info.minor}'
    hints = [
        'nvPY requires tkinter, but it is not available in this Python installation.',
    ]
    if platform.system() == 'Darwin':
        hints.append(f'On macOS with Homebrew Python: brew install python-tk@{ver}')
    elif platform.system() == 'Linux':
        hints.append('On Debian/Ubuntu: sudo apt-get install python3-tk')
        hints.append(f'On Fedora/RHEL: sudo dnf install python{ver}-tkinter')
    else:
        hints.append('Reinstall Python with Tcl/Tk support enabled.')
    return ImportError('\n'.join(hints))


try:
    from tkinter import *
    from tkinter.ttk import *  # type:ignore
except ImportError as exc:
    raise _tkinter_missing_error(exc) from exc

from .tk_support import with_ucs4_error_handling

########################################################################
# Apply the monkey patches for convert TclError to Ucs4NotSupportedError

_Text = Text  # type: ignore
del Text  # type: ignore


class Text(_Text):  # type:ignore

    @with_ucs4_error_handling
    def insert(self, *args, **kwargs):
        return _Text.insert(self, *args, **kwargs)
