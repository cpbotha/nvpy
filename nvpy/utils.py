# nvPY: cross-platform note-taking app with simplenote syncing
# copyright 2012 by Charl P. Botha <cpbotha@vxlabs.com>
# new BSD license
import datetime
import random
import re
from urllib.error import URLError
from urllib.request import urlopen
from queue import Queue, Empty as QueueEmpty
import threading

from . import tk

# first line with non-whitespace should be the title
note_title_re = re.compile('\s*(.*)\n?')


def generate_random_key():
    """Generate random 30 digit (15 byte) hex string.

    stackoverflow question 2782229
    """
    return '%030x' % (random.randrange(256**15), )


def get_note_title(note):
    mo = note_title_re.match(note.get('content', ''))
    if mo:
        return mo.groups()[0]
    else:
        return ''


def get_note_title_file(note, replace_filename_spaces):
    mo = note_title_re.match(note.get('content', ''))
    if mo:
        fn = mo.groups()[0]
        if replace_filename_spaces:
            fn = fn.replace(' ', '_')
        fn = fn.replace('/', '_')
        if not fn:
            return ''

        if note_markdown(note):
            fn += '.mkdn'
        else:
            fn += '.txt'

        return fn
    else:
        return ''


def human_date(timestamp):
    """
    Given a timestamp, return pretty human format representation.

    For example, if timestamp is:
    * today, then do "15:11"
    * else if it is this year, then do "Aug 4"
    * else do "Dec 11, 2011"
    """

    # this will also give us timestamp in the local timezone
    dt = datetime.datetime.fromtimestamp(timestamp)
    # this returns localtime
    now = datetime.datetime.now()

    if dt.date() == now.date():
        # today: 15:11
        return dt.strftime('%H:%M')

    elif dt.year == now.year:
        # this year: Aug 6
        # format code %d unfortunately 0-pads
        return dt.strftime('%b') + ' ' + str(dt.day)

    else:
        # not today or this year, so we do "Dec 11, 2011"
        return '%s %d, %d' % (dt.strftime('%b'), dt.day, dt.year)


def note_pinned(n):
    asystags = n.get('systemtags', 0)
    # no systemtag at all
    if not asystags:
        return 0

    if 'pinned' in asystags:
        return 1
    else:
        return 0


def note_markdown(n):
    asystags = n.get('systemtags', 0)
    # no systemtag at all
    if not asystags:
        return 0

    if 'markdown' in asystags:
        return 1
    else:
        return 0


tags_illegal_chars = re.compile(r'[\s]')


def sanitise_tags(tags: str):
    """
    Given a string containing comma-separated tags, sanitise and return a list of string tags.

    The simplenote API doesn't allow for spaces, so we strip those out.

    @param tags: Comma-separated tags, one string.
    @returns: List of strings.
    """

    # hack out all kinds of whitespace, then split on ,
    # if you run into more illegal characters (simplenote does not want to sync them)
    # add them to the regular expression above.
    illegals_removed = tags_illegal_chars.sub('', tags)
    if len(illegals_removed) == 0:
        # special case for empty string ''
        # split turns that into [''], which is not valid
        return []

    else:
        return illegals_removed.split(',')


def check_internet_on():
    """Utility method to check if we have an internet connection.

    slightly adapted from: http://stackoverflow.com/a/3764660/532513
    """
    try:
        urlopen('http://74.125.228.100', timeout=1)
        return True

    except URLError:
        pass

    return False


class SubjectMixin:
    """Maintain a list of callables for each event type.

    We follow the convention action:object, e.g. change:entry.
    """

    # main thread object
    MAIN_THREAD = threading.main_thread()

    def __init__(self):
        self.observers = {}
        self.mutes = {}
        self.notifies = Queue()

    def add_observer(self, evt_type, o):
        from .debug import wrap_buggy_function
        o = tk.with_ucs4_error_handling(o)
        o = wrap_buggy_function(o)

        if evt_type not in self.observers:
            self.observers[evt_type] = [o]

        elif o not in self.observers[evt_type]:
            self.observers[evt_type].append(o)

    def notify_observers(self, evt_type, evt):
        if evt_type in self.mutes or evt_type not in self.observers:
            return

        if threading.current_thread() == self.MAIN_THREAD:
            for o in self.observers[evt_type]:
                self.__invoke_observer(o, evt_type, evt)

        else:
            # Tkinter is not thread safe. so, observers must be executed on MAIN_THREAD.
            self.notifies.put((evt_type, evt))

    def handle_notifies(self):
        """Do processing to queued notifies.
        
        This method is periodically called from main thread.
        """
        assert threading.current_thread() == self.MAIN_THREAD
        try:
            while True:
                evt_type, evt = self.notifies.get_nowait()

                for o in self.observers[evt_type]:
                    self.__invoke_observer(o, evt_type, evt)

        except QueueEmpty:
            pass

    def __invoke_observer(self, observer, event_type, event):
        # invoke observers with ourselves as first param
        observer(self, event_type, event)

    def mute(self, evt_type):
        self.mutes[evt_type] = True

    def unmute(self, evt_type):
        if evt_type in self.mutes:
            del self.mutes[evt_type]
