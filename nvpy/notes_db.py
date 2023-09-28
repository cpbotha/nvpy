# nvPY: cross-platform note-taking app with simplenote syncing
# copyright 2012 by Charl P. Botha <cpbotha@vxlabs.com>
# new BSD license
""" nvPY internal database and note synchronization logic """

import sys
import codecs
import copy
import glob
import os
import json
import logging
import abc
import unicodedata
import pathlib
import threading
from queue import Queue, Empty
from http.client import HTTPException
from threading import Thread, Lock
import time
import typing
import re
import base64

import simplenote  # type:ignore

from . import events
from . import utils
from . import nvpy
from .debug import wrap_buggy_function

FilterResult = typing.Tuple[typing.List['NoteInfo'], typing.Optional[typing.Pattern], int]

# API key provided for nvPY.
# Please do not use for other software!
simplenote.simplenote.API_KEY = bytes(reversed(base64.b64decode('OTg0OTI4ZTg4YjY0NzMyOTZjYzQzY2IwMDI1OWFkMzg=')))


# workaround for https://github.com/cpbotha/nvpy/issues/191
class Simplenote(simplenote.Simplenote):

    def get_token(self):
        if self.token is None:
            self.token = self.authenticate(self.username, self.password)
            if self.token is None:
                raise HTTPException('failed to connect to the server')
        try:
            return str(self.token, 'utf-8')
        except TypeError:
            return self.token

    def get_note(self, *args, **kwargs):
        try:
            return super().get_note(*args, **kwargs)
        except HTTPException as e:
            return e, -1

    def update_note(self, *args, **kwargs):
        try:
            return super().update_note(*args, **kwargs)
        except HTTPException as e:
            return e, -1

    def get_note_list(self, *args, **kwargs):
        try:
            return super().get_note_list(*args, **kwargs)
        except HTTPException as e:
            return e, -1


ACTION_SAVE = 0
ACTION_SYNC_PARTIAL_TO_SERVER = 1
ACTION_SYNC_PARTIAL_FROM_SERVER = 2  # UNUSED.


class SyncError(RuntimeError):
    pass


class ReadError(RuntimeError):
    pass


class WriteError(RuntimeError):
    pass


class UpdateResult(typing.NamedTuple):
    # Note object
    note: typing.Any
    is_updated: bool
    # Usually, error_object is None.  When failed to update, it have an error object.
    error_object: typing.Optional[typing.Any]


class NoteStatus(typing.NamedTuple):
    saved: bool
    synced: bool
    modified: bool
    full_syncing: bool


class NoteInfo(typing.NamedTuple):
    key: str
    note: typing.Any
    tagfound: int


class _BackgroundTask(typing.NamedTuple):
    action: int
    key: str
    note: typing.Any


class _BackgroundTaskReslt(typing.NamedTuple):
    action: int
    key: str
    note: typing.Any
    error: int


class Sorter(abc.ABC):
    """ The abstract class to build extensible and flexible sorting logic.

    Usage:
        >>> sorter = MergedSorter(PinnedSorter(), AlphaSorter())
        >>> notes.sort(key=sorter)
    """

    @abc.abstractmethod
    def __call__(self, o: NoteInfo):
        raise NotImplementedError()


class NopSorter(Sorter):
    """ Do nothing. The notes list retain original order. Use it to simplify complex sort logic. """

    def __call__(self, o: NoteInfo):
        return 0


class MergedSorter(Sorter):
    """ Merge multiple sorters into a sorter. It realize sorting notes by multiple keys. """

    def __init__(self, *sorters: Sorter):
        self.sorters = sorters

    def __call__(self, o: NoteInfo):
        return tuple(s(o) for s in self.sorters)


class PinnedSorter(Sorter):
    """ Sort that pinned notes are on top. """

    def __call__(self, o: NoteInfo):
        # Pinned notes on top.
        return 0 if utils.note_pinned(o.note) else 1


class AlphaSorter(Sorter):
    """ Sort in alphabetically on note title. """

    def __call__(self, o: NoteInfo):
        return utils.get_note_title(o.note)


T = typing.TypeVar('T')


class AlphaNumSorter(Sorter):
    """ Sort in alphanumeric order on note title. """

    class Nullable(typing.Generic[T]):
        """ Null-safe comparable object for any types.

        Built-in types can not compare with None. For example, if you try to execute `1 < None`, it will raise a
        TypeError. The Nullable solves this problem, and further simplifies of comparison logic.
        """

        @classmethod
        def __class_getitem__(cls, item):
            return typing.TypeAlias(AlphaNumSorter.Nullable)

        def __init__(self, val):
            self.val = val

        def __eq__(self, other):
            if not isinstance(other, AlphaNumSorter.Nullable):
                return NotImplemented
            return self.val == other.val

        def __gt__(self, other):
            if not isinstance(other, AlphaNumSorter.Nullable):
                return NotImplemented
            if self.val is None:
                return False
            else:
                if other.val is None:
                    return True
                return self.val > other.val

        def __repr__(self):
            return f'Nullable({repr(self.val)})'

    class Element(typing.NamedTuple):
        digits: 'AlphaNumSorter.Nullable[int]'
        letters: 'AlphaNumSorter.Nullable[str]'
        other: 'AlphaNumSorter.Nullable[str]'

    def _enumerate_chars_with_category(self, s: str):
        for c in s:
            category = unicodedata.category(c)
            if category == 'Nd':
                yield 'numeric', c
            elif category[0] == 'N' or category[0] == 'L':
                yield 'letter', c
            else:
                yield 'other', c

    def _make_groups(self, iter_):
        # 連続した同じグループをグループ化
        s = ''
        last_category = ''
        for category, c in iter_:
            if last_category == category:
                s += c
            elif last_category != '':
                yield last_category, s
                last_category = category
                s = c
            elif last_category == '':
                last_category = category
                s = c
            else:
                raise RuntimeError('bug')
        yield last_category, s

    def _str2elements(self, s: str):
        if s == '':
            # The _make_groups() will yield an empty string ('') if s is ''. This behavior causes a crash on this
            # function. We should handle this case before executing _make_gropus().
            return AlphaNumSorter.Element(
                digits=AlphaNumSorter.Nullable(None),
                letters=AlphaNumSorter.Nullable(None),
                other=AlphaNumSorter.Nullable(None),
            )
        iter_ = self._enumerate_chars_with_category(s)
        groups = self._make_groups(iter_)
        for category, s in groups:
            digits = None
            letters = None
            others = None
            if category == 'numeric':
                digits = int(s)
            elif category == 'letter':
                letters = s
            elif category == 'other':
                others = s
            else:
                raise RuntimeError('bug')
            yield AlphaNumSorter.Element(
                digits=AlphaNumSorter.Nullable(digits),
                letters=AlphaNumSorter.Nullable(letters),
                other=AlphaNumSorter.Nullable(others),
            )

    def __call__(self, o: NoteInfo):
        title = utils.get_note_title(o.note)
        return tuple(self._str2elements(title))


class DateSorter(Sorter):
    """ Sort in creation/modification date. """

    def __init__(self, mode: 'nvpy.SortMode'):
        if mode == nvpy.SortMode.MODIFICATION_DATE:
            self._sort_key = self._sort_key_modification_date
        elif mode == nvpy.SortMode.CREATION_DATE:
            self._sort_key = self._sort_key_creation_date
        else:
            raise ValueError(f'invalid sort mode: {mode}')
        self.mode = mode

    def __call__(self, o: NoteInfo):
        return self._sort_key(o.note)

    def _sort_key_modification_date(self, note):
        # Last modified on top
        return -float(note.get('modifydate', 0))

    def _sort_key_creation_date(self, note):
        # Last modified on top
        return -float(note.get('createdate', 0))


class NotesDB(utils.SubjectMixin):
    """NotesDB will take care of the local notes database and syncing with SN.
    """

    def __init__(self, config: 'nvpy.Config'):
        utils.SubjectMixin.__init__(self)

        self.config = config

        # create db dir if it does not exist
        if not os.path.exists(config.db_path):
            os.mkdir(config.db_path)

        self.db_path = config.db_path

        # create txt Notes dir if it does not exist
        if self.config.notes_as_txt and not os.path.exists(config.txt_path):
            os.mkdir(config.txt_path)

        now = time.time()
        # now read all .json files from disk
        fnlist = glob.glob(self.helper_key_to_fname('*'))
        txtlist = []

        for ext in config.read_txt_extensions.split(','):
            txtlist += glob.glob(self.config.txt_path + '/*.' + ext)

        # removing json files and force full full sync if using text files
        # and none exists and json files are there
        if self.config.notes_as_txt and not txtlist and fnlist:
            logging.debug('Forcing resync: using text notes, first usage')
            for fn in fnlist:
                os.unlink(fn)
            fnlist = []

        self.notes = {}
        self.notes_lock = threading.Lock()

        if self.config.notes_as_txt:
            self.titlelist = {}

        for fn in fnlist:
            try:
                with open(fn, 'rb') as f:
                    n = json.load(f)
                if self.config.notes_as_txt:
                    nt = utils.get_note_title_file(n, self.config.replace_filename_spaces)
                    tfn = os.path.join(self.config.txt_path, nt)
                    if os.path.isfile(tfn):
                        self.titlelist[n.get('key')] = nt
                        txtlist.remove(tfn)
                        if os.path.getmtime(tfn) > os.path.getmtime(fn):
                            logging.debug('Text note was changed: %s' % (fn, ))
                            with codecs.open(tfn, mode='rb', encoding='utf-8') as f:
                                c = f.read()

                            n['content'] = c
                            n['modifydate'] = os.path.getmtime(tfn)
                    else:
                        logging.debug('Deleting note : %s' % (fn, ))
                        if not self.config.simplenote_sync:
                            os.unlink(fn)
                            continue
                        else:
                            n['deleted'] = 1
                            n['modifydate'] = now

            except IOError as e:
                logging.error('NotesDB_init: Error opening %s: %s' % (fn, str(e)))
                raise ReadError('Error opening note file')

            except ValueError as e:
                logging.error('NotesDB_init: Error reading %s: %s' % (fn, str(e)))
                raise ReadError('Error reading note file')

            else:
                # we always have a localkey, also when we don't have a note['key'] yet (no sync)
                localkey = os.path.splitext(os.path.basename(fn))[0]
                self.notes[localkey] = n
                # we maintain in memory a timestamp of the last save
                # these notes have just been read, so at this moment
                # they're in sync with the disc.
                n['savedate'] = now

        if self.config.notes_as_txt:
            for fn in txtlist:
                logging.debug('New text note found : %s' % (fn, ))
                tfn = os.path.join(self.config.txt_path, fn)
                try:
                    with codecs.open(tfn, mode='rb', encoding='utf-8') as f:
                        c = f.read()

                except IOError as e:
                    logging.error('NotesDB_init: Error opening %s: %s' % (fn, str(e)))
                    raise ReadError('Error opening note file')

                except ValueError as e:
                    logging.error('NotesDB_init: Error reading %s: %s' % (fn, str(e)))
                    raise ReadError('Error reading note file')

                else:
                    nk = self.create_note(c)
                    nn = os.path.splitext(os.path.basename(fn))[0]
                    if nn != utils.get_note_title(self.notes[nk]):
                        self.notes[nk]['content'] = nn + "\n\n" + c

                    os.unlink(tfn)

        # save and sync queue
        self.q_save: 'Queue[_BackgroundTask]' = Queue()
        self.q_save_res: 'Queue[_BackgroundTask]' = Queue()

        thread_save = Thread(target=wrap_buggy_function(self.worker_save))
        thread_save.daemon = True
        thread_save.start()

        self.full_syncing = False

        # initialise the simplenote instance we're going to use
        # this does not yet need network access
        if self.config.simplenote_sync:
            self.simplenote = Simplenote(config.sn_username, config.sn_password)

            # reading a variable or setting this variable is atomic
            # so sync thread will write to it, main thread will only
            # check it sometimes.
            self.waiting_for_simplenote = False

            self.syncing_lock = Lock()

            self.q_sync: 'Queue[_BackgroundTask]' = Queue()
            self.q_sync_res: 'Queue[_BackgroundTaskReslt]' = Queue()

            thread_sync = Thread(target=wrap_buggy_function(self.worker_sync))
            thread_sync.daemon = True
            thread_sync.start()

    def create_note(self, title):
        # need to get a key unique to this database. not really important
        # what it is, as long as it's unique.
        new_key = utils.generate_random_key()
        while new_key in self.notes:
            new_key = utils.generate_random_key()

        timestamp = time.time()

        # note has no internal key yet.
        new_note = {
            'content': title,
            'modifydate': timestamp,
            'createdate': timestamp,
            'savedate': 0,  # never been written to disc
            'syncdate': 0,  # never been synced with server
            'tags': []
        }

        self.notes[new_key] = new_note

        return new_key

    def delete_note(self, key):
        n = self.notes[key]
        n['deleted'] = 1
        n['modifydate'] = time.time()

    def filter_notes(self, search_string=None) -> FilterResult:
        """Return list of notes filtered with search string.

        Based on the search mode that has been selected in self.config,
        this method will call the appropriate helper method to do the
        actual work of filtering the notes.

        @param search_string: String that will be used for searching.
         Different meaning depending on the search mode.
        @return: notes filtered with selected search mode and sorted according
        to configuration. Two more elements in tuple: a regular expression
        that can be used for highlighting strings in the text widget; the
        total number of notes in memory.
        """

        if self.config.search_mode == 'regexp':
            filtered_notes, match_regexp, active_notes = self.filter_notes_regexp(search_string)
        else:
            filtered_notes, match_regexp, active_notes = self.filter_notes_gstyle(search_string)

        filtered_notes.sort(key=self.config.sorter)
        return filtered_notes, match_regexp, active_notes

    def _helper_gstyle_tagmatch(self, tag_pats, note):
        if tag_pats:
            tags = note.get('tags')

            # tag: patterns specified, but note has no tags, so no match
            if not tags:
                return 0

            # for each tag_pat, we have to find a matching tag
            for tp in tag_pats:
                # at the first match between tp and a tag:
                if next((tag for tag in tags if tag.startswith(tp)), None) is not None:
                    # we found a tag that matches current tagpat, so we move to the next tagpat
                    continue

                else:
                    # we found no tag that matches current tagpat, so we break out of for loop
                    break

            else:
                # for loop never broke out due to no match for tagpat, so:
                # all tag_pats could be matched, so note is a go.
                return 1

            # break out of for loop will have us end up here
            # for one of the tag_pats we found no matching tag
            return 0

        else:
            # match because no tag: patterns were specified
            return 2

    def _helper_gstyle_mswordmatch(self, msword_pats, content):
        """If all words / multi-words in msword_pats are found in the content,
        the note goes through, otherwise not.

        @param msword_pats:
        @param content:
        @return:
        """

        # no search patterns, so note goes through
        if not msword_pats:
            return True

        # search for the first p that does NOT occur in content
        if next((p for p in msword_pats if p not in content), None) is None:
            # we only found pats that DO occur in content so note goes through
            return True

        else:
            # we found the first p that does not occur in content
            return False

    def filter_notes_gstyle(self, search_string=None) -> FilterResult:
        filtered_notes = []
        # total number of notes, excluding deleted
        active_notes = 0

        if not search_string:
            with self.notes_lock:
                for k in self.notes:
                    n = self.notes[k]
                    if not n.get('deleted'):
                        active_notes += 1
                        filtered_notes.append(NoteInfo(key=k, note=n, tagfound=0))

            return filtered_notes, None, active_notes

        # group0: ag - not used
        # group1: t(ag)?:([^\s]+)
        # group2: multiple words in quotes
        # group3: single words
        # example result for 't:tag1 t:tag2 word1 "word2 word3" tag:tag3' ==
        # [('', 'tag1', '', ''), ('', 'tag2', '', ''), ('', '', '', 'word1'), ('', '', 'word2 word3', ''), ('ag', 'tag3', '', '')]

        groups = re.findall('t(ag)?:([^\s]+)|"([^"]+)"|([^\s]+)', search_string)
        tms_pats: typing.List[typing.List[str]] = [[] for _ in range(3)]

        # we end up with [[tag_pats],[multi_word_pats],[single_word_pats]]
        for gi in groups:
            for mi in range(1, 4):
                if gi[mi]:
                    tms_pats[mi - 1].append(gi[mi])

        with self.notes_lock:
            for k in self.notes:
                n = self.notes[k]

                if not n.get('deleted'):
                    active_notes += 1
                    c = n.get('content')

                    # case insensitive mode: WARNING - SLOW!
                    if not self.config.case_sensitive and c:
                        c = c.lower()

                    tagmatch = self._helper_gstyle_tagmatch(tms_pats[0], n)
                    # case insensitive mode: WARNING - SLOW!
                    msword_pats = tms_pats[1] + tms_pats[2] if self.config.case_sensitive else [
                        p.lower() for p in tms_pats[1] + tms_pats[2]
                    ]
                    if tagmatch and self._helper_gstyle_mswordmatch(msword_pats, c):
                        # we have a note that can go through!

                        # tagmatch == 1 if a tag was specced and found
                        # tagmatch == 2 if no tag was specced (so all notes go through)
                        tagfound = 1 if tagmatch == 1 else 0
                        # we have to store our local key also
                        filtered_notes.append(NoteInfo(key=k, note=n, tagfound=tagfound))

        regexp = None
        if tms_pats[1] + tms_pats[2]:
            regexp_pattern = '|'.join(re.escape(p) for p in tms_pats[1] + tms_pats[2])
            regexp_flag = 0 if self.config.case_sensitive else re.I
            try:
                regexp = re.compile(regexp_pattern, regexp_flag)
            except re.error:
                logging.error('Failed to compile regular expression: %r', regexp_pattern)
        return filtered_notes, regexp, active_notes

    def filter_notes_regexp(self, search_string=None) -> FilterResult:
        """Return list of notes filtered with search_string,
        a regular expression, each a tuple with (local_key, note).
        """

        sspat: typing.Optional[typing.Pattern]
        if search_string:
            try:
                if self.config.case_sensitive == 0:
                    sspat = re.compile(search_string, re.MULTILINE | re.I)
                else:
                    sspat = re.compile(search_string, re.MULTILINE)
            except re.error:
                sspat = None

        else:
            sspat = None

        filtered_notes = []
        # total number of notes, excluding deleted ones
        active_notes = 0
        with self.notes_lock:
            for k in self.notes:
                n = self.notes[k]
                # we don't do anything with deleted notes (yet)
                if n.get('deleted'):
                    continue

                active_notes += 1

                c = n.get('content')
                if self.config.search_tags == 1:
                    t = n.get('tags')
                    if sspat:
                        if t and any(filter(lambda ti: sspat.search(ti), t)):  # type:ignore
                            # we have to store our local key also
                            filtered_notes.append(NoteInfo(key=k, note=n, tagfound=1))

                        elif sspat.search(c):
                            # we have to store our local key also
                            filtered_notes.append(NoteInfo(key=k, note=n, tagfound=0))

                    else:
                        # we have to store our local key also
                        filtered_notes.append(NoteInfo(key=k, note=n, tagfound=0))
                else:
                    if not sspat or sspat.search(c):
                        # we have to store our local key also
                        filtered_notes.append(NoteInfo(key=k, note=n, tagfound=0))

        return filtered_notes, sspat, active_notes

    def get_note(self, key):
        return self.notes[key]

    def get_note_content(self, key):
        with self.notes_lock:
            return self.notes[key].get('content')

    def get_note_status(self, key):
        saved, synced, modified = False, False, False
        if key is not None:
            n = self.notes[key]
            modifydate = float(n['modifydate'])
            savedate = float(n['savedate'])

            if savedate > modifydate:
                saved = True
            else:
                modified = True

            if float(n['syncdate']) > modifydate:
                synced = True

        return NoteStatus(saved=saved, synced=synced, modified=modified, full_syncing=self.full_syncing)

    def get_save_queue_len(self):
        return self.q_save.qsize()

    def get_sync_queue_len(self):
        return self.q_sync.qsize()

    def is_worker_busy(self):
        return bool(self.q_sync.qsize() or self.syncing_lock.locked() or self.waiting_for_simplenote
                    or self.q_save.qsize())

    def helper_key_to_fname(self, k):
        return os.path.join(self.db_path, k) + '.json'

    def helper_save_note(self, k, note):
        """Save a single note to disc.

        """

        if self.config.notes_as_txt:
            t = utils.get_note_title_file(note, self.config.replace_filename_spaces)
            if t and not note.get('deleted'):
                if k in self.titlelist:
                    logging.debug('Writing note : %s %s' % (t, self.titlelist[k]))
                    if self.titlelist[k] != t:
                        dfn = os.path.join(self.config.txt_path, self.titlelist[k])
                        if os.path.isfile(dfn):
                            logging.debug('Delete file %s ' % (dfn, ))
                            os.unlink(dfn)
                        else:
                            logging.debug('File not exits %s ' % (dfn, ))
                else:
                    logging.debug('Key not in list %s ' % (k, ))

                self.titlelist[k] = t
                fn = os.path.join(self.config.txt_path, t)
                try:
                    pathlib.Path(fn).write_text(note['content'], encoding='utf-8')
                except (IOError, ValueError) as e:
                    logging.error('NotesDB_save: Error writing %s: %s' % (fn, str(e)))
                    raise WriteError(f'Error writing note file ({fn})')

            elif t and note.get('deleted') and k in self.titlelist:
                dfn = os.path.join(self.config.txt_path, self.titlelist[k])
                if os.path.isfile(dfn):
                    logging.debug('Delete file %s ' % (dfn, ))
                    os.unlink(dfn)

        fn = self.helper_key_to_fname(k)
        if not self.config.simplenote_sync and note.get('deleted'):
            if os.path.isfile(fn):
                os.unlink(fn)
        else:
            try:
                pathlib.Path(fn).write_text(json.dumps(note, indent=2), encoding='utf-8')
            except (IOError, ValueError) as e:
                logging.error('NotesDB_save: Error opening %s: %s' % (fn, str(e)))
                raise WriteError(f'Error writing note file ({fn})')

        # record that we saved this to disc.
        note['savedate'] = time.time()

    def sync_note_unthreaded(self, k):
        """Sync a single note with the server.

        Update existing note in memory with the returned data.
        This is a sychronous (blocking) call.
        """

        note = self.notes[k]

        if Note(note).need_sync_to_server:
            # update to server
            result = self.update_note_to_server(note)

            if result.error_object is None:
                # success!
                n = result.note

                # if content was unchanged, there'll be no content sent back!
                new_content = 'content' in n

                now = time.time()
                # 1. store when we've synced
                n['syncdate'] = now

                # update our existing note in-place!
                note.update(n)

                # return the key
                return (k, new_content)

            else:
                return None

        else:
            # our note is synced up, but we check if server has something new for us
            gret = self.simplenote.get_note(note['key'])

            if gret[1] == 0:
                n = gret[0]

                if Note(n).is_newer_than(note):
                    n['syncdate'] = time.time()
                    note.update(n)
                    return (k, True)

                else:
                    return (k, False)

            else:
                return None

    def save_threaded(self):
        with self.notes_lock:
            for k, n in self.notes.items():
                if Note(n).need_save:
                    cn = copy.deepcopy(n)
                    # put it on my queue as a save
                    o = _BackgroundTask(action=ACTION_SAVE, key=k, note=cn)
                    self.q_save.put(o)

        # in this same call, we process stuff that might have been put on the result queue
        nsaved = 0
        something_in_queue = True
        while something_in_queue:
            try:
                o = self.q_save_res.get_nowait()

            except Empty:
                something_in_queue = False

            else:
                # o (.action, .key, .note) is something that was written to disk
                # we only record the savedate.
                self.notes[o.key]['savedate'] = o.note['savedate']
                self.notify_observers('change:note-status', events.NoteStatusChangedEvent(what='savedate', key=o.key))
                self.notify_observers('saved:note', events.NoteSavedEvent(key=o.key))
                nsaved += 1

        return nsaved

    def sync_to_server_threaded(self, wait_for_idle=True):
        """Only sync notes that have been changed / created locally since previous sync.

        This function is called by the housekeeping handler, so once every
        few seconds.

        @param wait_for_idle: Usually, last modification date has to be more
        than a few seconds ago before a sync to server is attempted. If
        wait_for_idle is set to False, no waiting is applied. Used by exit
        cleanup in controller.

        """
        # this many seconds of idle time (i.e. modification this long ago)
        # before we try to sync.
        if wait_for_idle:
            lastmod = 3
        else:
            lastmod = 0

        if not self.syncing_lock.acquire(blocking=False):
            # Currently, syncing_lock is locked by other thread.
            return 0, 0

        try:
            with self.notes_lock:
                now = time.time()
                for k, n in self.notes.items():
                    # if note has been modified since the sync, we need to sync.
                    # only do so if note hasn't been touched for 3 seconds
                    # and if this note isn't still in the queue to be processed by the
                    # worker (this last one very important)
                    modifydate = float(n.get('modifydate', -1))
                    syncdate = float(n.get('syncdate', -1))
                    need_sync = modifydate > syncdate and now - modifydate > lastmod
                    if need_sync:
                        task = _BackgroundTask(action=ACTION_SYNC_PARTIAL_TO_SERVER, key=k, note=None)
                        self.q_sync.put(task)

            # in this same call, we read out the result queue
            nsynced = 0
            nerrored = 0
            while True:
                try:
                    o: _BackgroundTaskReslt
                    o = self.q_sync_res.get_nowait()
                except Empty:
                    break

                okey = o.key
                if o.error:
                    nerrored += 1
                    continue

                # notify anyone (probably nvPY) that this note has been changed
                self.notify_observers('synced:note', events.NoteSyncedEvent(lkey=okey))

                nsynced += 1
                self.notify_observers('change:note-status', events.NoteStatusChangedEvent(what='syncdate', key=okey))

            return (nsynced, nerrored)
        finally:
            self.syncing_lock.release()

    def sync_full_threaded(self):
        thread_sync_full = Thread(target=self.sync_full_unthreaded)
        thread_sync_full.daemon = True
        thread_sync_full.start()

    def sync_full_unthreaded(self):
        """Perform a full bi-directional sync with server.

        After this, it could be that local keys have been changed, so
        reset any views that you might have.
        """

        try:
            self.syncing_lock.acquire()

            self.full_syncing = True
            local_deletes = {}

            self.notify_observers('progress:sync_full', events.SyncProgressEvent(msg='Starting full sync.'))
            # 1. Synchronize notes when it has locally changed.
            #    In this phase, synchronized all notes from client to server.
            with self.notes_lock:
                modified_notes = list(filter(lambda lk: Note(self.notes[lk]).need_sync_to_server, self.notes.keys()))
            for ni, lk in enumerate(modified_notes):
                with self.notes_lock:
                    n = self.notes[lk]
                if not Note(n).need_sync_to_server:
                    continue

                result = self.update_note_to_server(n)
                if result.error_object is None:
                    with self.notes_lock:
                        # replace n with result.note.
                        # if this was a new note, our local key is not valid anymore
                        del self.notes[lk]
                        # in either case (new or existing note), save note at assigned key
                        k = result.note.get('key')
                        # we merge the note we got back (content could be empty!)
                        n.update(result.note)
                        # and put it at the new key slot
                        self.notes[k] = n

                    # record that we just synced
                    n['syncdate'] = time.time()

                    # whatever the case may be, k is now updated
                    self.helper_save_note(k, n)
                    if lk != k:
                        # if lk was a different (purely local) key, should be deleted
                        local_deletes[lk] = True

                    self.notify_observers(
                        'progress:sync_full',
                        events.SyncProgressEvent(msg='Synced modified note %d/%d to server.' %
                                                 (ni, len(modified_notes))))

                else:
                    key = n.get('key') or lk
                    msg = "Sync step 1 error - Could not update note {0} to server: {1}".format(
                        key, str(result.error_object))
                    logging.error(msg)
                    raise SyncError(msg)

            # 2. Retrieves full note list from server.
            #    In phase 2 to 5, synchronized all notes from server to client.
            self.notify_observers(
                'progress:sync_full',
                events.SyncProgressEvent(msg='Retrieving full note list from server, could take a while.'))
            self.waiting_for_simplenote = True
            nl = self.simplenote.get_note_list(data=False)
            self.waiting_for_simplenote = False
            if nl[1] == 0:
                nl = nl[0]
                self.notify_observers('progress:sync_full',
                                      events.SyncProgressEvent(msg='Retrieved full note list from server.'))

            else:
                error = nl[0]
                msg = 'Could not get note list from server: %s' % str(error)
                logging.error(msg)
                raise SyncError(msg)

            # 3. Delete local notes not included in full note list.
            server_keys = {}
            for n in nl:
                k = n.get('key')
                server_keys[k] = True

            with self.notes_lock:
                for lk in list(self.notes.keys()):
                    if lk not in server_keys:
                        if self.notes[lk]['syncdate'] == 0:
                            # This note MUST NOT delete because it was created during phase 1 or phase 2.
                            continue

                        if self.config.notes_as_txt:
                            tfn = os.path.join(
                                self.config.txt_path,
                                utils.get_note_title_file(self.notes[lk], self.config.replace_filename_spaces))
                            if os.path.isfile(tfn):
                                os.unlink(tfn)
                        del self.notes[lk]
                        local_deletes[lk] = True

            self.notify_observers('progress:sync_full',
                                  events.SyncProgressEvent(msg='Deleted note %d.' % (len(local_deletes))))

            # 4. Update local notes.
            lennl = len(nl)
            sync_from_server_errors = 0
            for ni, n in enumerate(nl):
                k = n.get('key')
                if k in self.notes:
                    # n is already exists in local.
                    if Note(n).is_newer_than(self.notes[k]):
                        # We must update local note with remote note.
                        err = 0
                        if 'content' not in n:
                            # The content field is missing.  Get all data from server.
                            self.waiting_for_simplenote = True
                            n, err = self.simplenote.get_note(k)
                            self.waiting_for_simplenote = False

                        if err == 0:
                            self.notes[k].update(n)
                            self.notes[k]['syncdate'] = time.time()
                            self.helper_save_note(k, self.notes[k])
                            self.notify_observers(
                                'progress:sync_full',
                                events.SyncProgressEvent(msg='Synced newer note %d (%d) from server.' % (ni, lennl)))

                        else:
                            err_obj = n
                            logging.error('Error syncing newer note %s from server: %s' % (k, err_obj))
                            sync_from_server_errors += 1

                else:
                    # n is new note.
                    # We must save it in local.
                    err = 0
                    if 'content' not in n:
                        # The content field is missing.  Get all data from server.
                        self.waiting_for_simplenote = True
                        n, err = self.simplenote.get_note(k)
                        self.waiting_for_simplenote = False

                    if err == 0:
                        with self.notes_lock:
                            self.notes[k] = n
                            n['savedate'] = 0  # never been written to disc
                            n['syncdate'] = time.time()
                            self.helper_save_note(k, n)
                            self.notify_observers(
                                'progress:sync_full',
                                events.SyncProgressEvent(msg='Synced new note %d (%d) from server.' % (ni, lennl)))

                    else:
                        err_obj = n
                        logging.error('Error syncing new note %s from server: %s' % (k, err_obj))
                        sync_from_server_errors += 1

            # 5. Clean up local notes.
            for dk in local_deletes.keys():
                fn = self.helper_key_to_fname(dk)
                if os.path.exists(fn):
                    os.unlink(fn)

            self.notify_observers('complete:sync_full', events.SyncCompletedEvent(errors=sync_from_server_errors))

        except Exception as e:
            # Report an error to UI thread.
            self.notify_observers('error:sync_full', events.SyncFailedEvent(error=e, exc_info=sys.exc_info()))

        finally:
            self.full_syncing = False
            self.syncing_lock.release()

    def set_note_content(self, key, content):
        n = self.notes[key]
        old_content = n.get('content')
        if content != old_content:
            n['content'] = content
            n['modifydate'] = time.time()
            self.notify_observers('change:note-status', events.NoteStatusChangedEvent(what='modifydate', key=key))

    def delete_note_tag(self, key, tag):
        note = self.notes[key]
        note_tags = note.get('tags')
        note_tags.remove(tag)
        note['tags'] = note_tags
        note['modifydate'] = time.time()
        self.notify_observers('change:note-status', events.NoteStatusChangedEvent(what='modifydate', key=key))

    def add_note_tags(self, key, comma_seperated_tags: str):
        new_tags = utils.sanitise_tags(comma_seperated_tags)
        note = self.notes[key]
        tags_set = set(note.get('tags')) | set(new_tags)
        note['tags'] = sorted(tags_set)
        note['modifydate'] = time.time()
        self.notify_observers('change:note-status', events.NoteStatusChangedEvent(what='modifydate', key=key))

    def set_note_pinned(self, key, pinned):
        n = self.notes[key]
        old_pinned = utils.note_pinned(n)
        if pinned != old_pinned:
            if 'systemtags' not in n:
                n['systemtags'] = []

            systemtags = n['systemtags']

            if pinned:
                # which by definition means that it was NOT pinned
                systemtags.append('pinned')

            else:
                systemtags.remove('pinned')

            n['modifydate'] = time.time()
            self.notify_observers('change:note-status', events.NoteStatusChangedEvent(what='modifydate', key=key))

    def is_different_note(self, local_note, remote_note):
        # for keeping original data.
        local_note = dict(local_note)
        remote_note = dict(remote_note)

        del local_note['savedate']
        del local_note['syncdate']

        # convert to hashable objects.
        for k, v in local_note.items():
            if isinstance(v, list):
                local_note[k] = tuple(v)
        for k, v in remote_note.items():
            if isinstance(v, list):
                remote_note[k] = tuple(v)

        # it will returns an empty set() if each notes is equals.
        return set(local_note.items()) ^ set(remote_note.items())

    def worker_save(self):
        while True:
            o = self.q_save.get()

            if o.action == ACTION_SAVE:
                # this will write the savedate into o.note
                # with filename o.key.json
                try:
                    self.helper_save_note(o.key, o.note)

                except WriteError as e:
                    logging.error('FATAL ERROR in access to file system')
                    print("FATAL ERROR: Check the nvpy.log")
                    os._exit(1)

                else:
                    # put the whole thing back into the result q
                    # now we don't have to copy, because this thread
                    # is never going to use o again.
                    # somebody has to read out the queue...
                    self.q_save_res.put(o)

    def worker_sync(self):
        while True:
            task: _BackgroundTask
            task = self.q_sync.get()
            with self.syncing_lock:
                if task.action == ACTION_SYNC_PARTIAL_TO_SERVER:
                    res = self._worker_sync_to_server(task.key)
                    self.q_sync_res.put(res)
                else:
                    raise RuntimeError(f'invalid action: {task.action}')

    def _worker_sync_to_server(self, key: str):
        """ Sync a note to server. It is internal function of worker_sync().
        Caller MUST acquire the syncing_lock, and MUST NOT acquire the notes_lock.
        """
        action = ACTION_SYNC_PARTIAL_TO_SERVER
        with self.notes_lock:
            syncdate = time.time()
            note = self.notes[key]
            if not Note(note).need_sync_to_server:
                # The note already synced with server.
                return _BackgroundTaskReslt(action=action, key=key, note=None, error=0)
            local_note = copy.deepcopy(note)

        if 'key' in local_note:
            logging.debug('Updating note %s (local key %s) to server.' % (local_note['key'], key))
        else:
            logging.debug('Sending new note (local key %s) to server.' % (key, ))

        result = self.update_note_to_server(local_note)
        if result.error_object is not None:
            return _BackgroundTaskReslt(action=action, key=key, note=None, error=1)

        with self.notes_lock:
            note = self.notes[key]
            remote_note = result.note
            if float(local_note['modifydate']) < float(note['modifydate']):
                # The user has changed a local note during sync with server. Just record version that we got from
                # simplenote server. If we don't do this, merging problems start happening.
                #
                # VERY importantly: also store the key. It could be that we've just created the note, but that the user
                # continued typing. We need to store the new server key, else we'll keep on sending new notes.
                note['version'] = remote_note['version']
                note['syncdate'] = syncdate
                note['key'] = remote_note['key']
                return _BackgroundTaskReslt(action=action, key=key, note=None, error=0)

            if result.is_updated:
                if remote_note.get('content', None) is None:
                    # If note has not been changed, we don't get content back. To prevent overriding of content,
                    # we should remove the content from remote_note.
                    remote_note.pop('content', None)
                note.update(remote_note)
            note['syncdate'] = syncdate
            return _BackgroundTaskReslt(action=action, key=key, note=None, error=0)

    def update_note_to_server(self, note):
        """Update the note to simplenote server.

        :return: UpdateResult object
        """

        self.waiting_for_simplenote = True
        # WORKAROUND: simplenote <=v2.1.2 modifies the note passed by argument. To prevent on-memory database
        #             corruption, Copy the note object before it is passed to simplenote library.
        # https://github.com/cpbotha/nvpy/issues/181#issuecomment-489543782
        o, err = self.simplenote.update_note(note.copy())
        self.waiting_for_simplenote = False

        if err == 0:
            # success!

            # Keeps the internal fields of nvpy.
            new_note = dict(note)
            new_note.update(o)

            logging.debug('Server replies with updated note ' + new_note['key'])
            return UpdateResult(
                note=new_note,
                is_updated=True,
                error_object=None,
            )

        update_error = o

        if 'key' in note:
            # Note has already been saved on the simplenote server.
            # Try to recover the update error.
            self.waiting_for_simplenote = True
            o, err = self.simplenote.get_note(note['key'])
            self.waiting_for_simplenote = False

            if err == 0:
                local_note = note
                remote_note = o

                if not self.is_different_note(local_note, remote_note):
                    # got an error response when updating the note.
                    # however, the remote note has been updated.
                    # this phenomenon is rarely occurs.
                    # if it occurs, housekeeper's is going to repeatedly update this note.
                    # regard updating error as success for prevent this problem.
                    logging.info('Regard updating error (local key %s, error object %s) as success.' %
                                 (local_note["key"], repr(update_error)))
                    return UpdateResult(
                        note=local_note,
                        is_updated=False,
                        error_object=None,
                    )

                else:
                    # Local note and remote note are different.  But failed to update.
                    logging.error('Could not update note %s to server: %s, local=%s, remote=%s' %
                                  (note['key'], update_error, local_note, remote_note))
                    return UpdateResult(
                        note=None,
                        is_updated=False,
                        error_object=update_error,
                    )

            else:
                get_error = o
                logging.error('Could not get/update note %s: update_error=%s, get_error=%s' %
                              (note['key'], update_error, get_error))
                return UpdateResult(
                    note=None,
                    is_updated=False,
                    error_object={
                        'update_error': update_error,
                        'get_error': get_error
                    },
                )

        # Failed to create new note.
        assert err
        assert 'key' not in note
        return UpdateResult(note=None, is_updated=False, error_object=update_error)


class Note(dict):
    """ nvPY internal note representation

    The current implementation usually uses the dict type for note representation. It is hard to customize logic.
    We should migrate from the dict to the Note class.
    """

    @property
    def need_save(self):
        """Check if the local note need to save."""
        savedate = float(self['savedate'])
        return float(self['modifydate']) > savedate or float(self['syncdate']) > savedate

    @property
    def need_sync_to_server(self):
        """Check if the local note need to synchronize to the server.

        Return True when it has not key or it has been modified since last sync.
        """
        return 'key' not in self or float(self['modifydate']) > float(self['syncdate'])

    def is_newer_than(self, other):
        """ Return true if this note is newer than other note. """
        try:
            return float(self['modifydate']) > float(other['modifydate'])
        except KeyError:
            return self['version'] > other['version']
