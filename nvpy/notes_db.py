# nvPY: cross-platform note-taking app with simplenote syncing
# copyright 2012 by Charl P. Botha <cpbotha@vxlabs.com>
# new BSD license

import codecs
import copy
import glob
import os
import json
import logging
from Queue import Queue, Empty
import re
import simplenote
simplenote.NOTE_FETCH_LENGTH=100
from simplenote import Simplenote

from threading import Thread
import time
import utils

ACTION_SAVE = 0
ACTION_SYNC_PARTIAL_TO_SERVER = 1
ACTION_SYNC_PARTIAL_FROM_SERVER = 2 # UNUSED.

class SyncError(RuntimeError):
    pass

class ReadError(RuntimeError):
    pass

class WriteError(RuntimeError):
    pass

class NotesDB(utils.SubjectMixin):
    """NotesDB will take care of the local notes database and syncing with SN.
    """
    def __init__(self, config):
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
        txtlist = glob.glob(unicode(self.config.txt_path + '/*.txt', 'utf-8'))
        txtlist += glob.glob(unicode(self.config.txt_path + '/*.mkdn', 'utf-8'))

        # removing json files and force full full sync if using text files
        # and none exists and json files are there
        if self.config.notes_as_txt and not txtlist and fnlist:
            logging.debug('Forcing resync: using text notes, first usage')
            for fn in fnlist:
                os.unlink(fn)
            fnlist = []

        self.notes = {}
        if self.config.notes_as_txt:
            self.titlelist = {}

        for fn in fnlist:
            try:
                n = json.load(open(fn, 'rb'))
                if self.config.notes_as_txt:
                    nt = utils.get_note_title_file(n)
                    tfn = os.path.join(self.config.txt_path, nt)
                    if os.path.isfile(tfn):
                        self.titlelist[n.get('key')] = nt
                        txtlist.remove(tfn)
                        if os.path.getmtime(tfn) > os.path.getmtime(fn):
                            logging.debug('Text note was changed: %s' % (fn,))
                            with codecs.open(tfn, mode='rb', encoding='utf-8') as f:
                                c = f.read()

                            n['content'] = c
                            n['modifydate'] = os.path.getmtime(tfn)
                    else:
                        logging.debug('Deleting note : %s' % (fn,))
                        if not self.config.simplenote_sync:
                            os.unlink(fn)
                            continue
                        else:
                            n['deleted'] = 1
                            n['modifydate'] = now

            except IOError, e:
                logging.error('NotesDB_init: Error opening %s: %s' % (fn, str(e)))
                raise ReadError ('Error opening note file')

            except ValueError, e:
                logging.error('NotesDB_init: Error reading %s: %s' % (fn, str(e)))
                raise ReadError ('Error reading note file')

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
                logging.debug('New text note found : %s' % (fn),)
                tfn = os.path.join(self.config.txt_path, fn)
                try:
                    with codecs.open(tfn, mode='rb', encoding='utf-8') as f:
                        c = f.read()

                except IOError, e:
                    logging.error('NotesDB_init: Error opening %s: %s' % (fn, str(e)))
                    raise ReadError ('Error opening note file')

                except ValueError, e:
                    logging.error('NotesDB_init: Error reading %s: %s' % (fn, str(e)))
                    raise ReadError ('Error reading note file')

                else:
                    nk = self.create_note(c)
                    nn = os.path.splitext(os.path.basename(fn))[0]
                    if nn != utils.get_note_title(self.notes[nk]):
                        self.notes[nk]['content'] = nn + "\n\n" + c

                    os.unlink(tfn)


        # save and sync queue
        self.q_save = Queue()
        self.q_save_res = Queue()

        thread_save = Thread(target=self.worker_save)
        thread_save.setDaemon(True)
        thread_save.start()

        # initialise the simplenote instance we're going to use
        # this does not yet need network access
        if self.config.simplenote_sync:
            self.simplenote = Simplenote(config.sn_username, config.sn_password)

            # we'll use this to store which notes are currently being synced by
            # the background thread, so we don't add them anew if they're still
            # in progress. This variable is only used by the background thread.
            self.threaded_syncing_keys = {}

            # reading a variable or setting this variable is atomic
            # so sync thread will write to it, main thread will only
            # check it sometimes.
            self.waiting_for_simplenote = False

            self.q_sync = Queue()
            self.q_sync_res = Queue()

            thread_sync = Thread(target=self.worker_sync)
            thread_sync.setDaemon(True)
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
                    'content' : title,
                    'modifydate' : timestamp,
                    'createdate' : timestamp,
                    'savedate' : 0, # never been written to disc
                    'syncdate' : 0, # never been synced with server
                    'tags' : []
                    }

        self.notes[new_key] = new_note

        return new_key

    def delete_note(self, key):
        n = self.notes[key]
        n['deleted'] = 1
        n['modifydate'] = time.time()

    def filter_notes(self, search_string=None):
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

        if self.config.sort_mode == 0:
            if self.config.pinned_ontop == 0:
                # sort alphabetically on title
                filtered_notes.sort(key=lambda o: utils.get_note_title(o.note))
            else:
                filtered_notes.sort(utils.sort_by_title_pinned)

        else:
            if self.config.pinned_ontop == 0:
                # last modified on top
                filtered_notes.sort(key=lambda o: -float(o.note.get('modifydate', 0)))
            else:
                filtered_notes.sort(utils.sort_by_modify_date_pinned, reverse=True)

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



    def filter_notes_gstyle(self, search_string=None):

        filtered_notes = []
        # total number of notes, excluding deleted
        active_notes = 0

        if not search_string:
            for k in self.notes:
                n = self.notes[k]
                if not n.get('deleted'):
                    active_notes += 1
                    filtered_notes.append(utils.KeyValueObject(key=k, note=n, tagfound=0))

            return filtered_notes, [], active_notes

        # group0: ag - not used
        # group1: t(ag)?:([^\s]+)
        # group2: multiple words in quotes
        # group3: single words
        # example result for 't:tag1 t:tag2 word1 "word2 word3" tag:tag3' ==
        # [('', 'tag1', '', ''), ('', 'tag2', '', ''), ('', '', '', 'word1'), ('', '', 'word2 word3', ''), ('ag', 'tag3', '', '')]

        groups = re.findall('t(ag)?:([^\s]+)|"([^"]+)"|([^\s]+)', search_string)
        tms_pats = [[] for _ in range(3)]

        # we end up with [[tag_pats],[multi_word_pats],[single_word_pats]]
        for gi in groups:
            for mi in range(1,4):
                if gi[mi]:
                    tms_pats[mi-1].append(gi[mi])

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
                msword_pats = tms_pats[1] + tms_pats[2] if self.config.case_sensitive else [p.lower() for p in tms_pats[1] + tms_pats[2]]
                if tagmatch and self._helper_gstyle_mswordmatch(msword_pats, c):
                    # we have a note that can go through!

                    # tagmatch == 1 if a tag was specced and found
                    # tagmatch == 2 if no tag was specced (so all notes go through)
                    tagfound = 1 if tagmatch == 1 else 0
                    # we have to store our local key also
                    filtered_notes.append(utils.KeyValueObject(key=k, note=n, tagfound=tagfound))

        return filtered_notes, '|'.join(tms_pats[1] + tms_pats[2]), active_notes


    def filter_notes_regexp(self, search_string=None):
        """Return list of notes filtered with search_string,
        a regular expression, each a tuple with (local_key, note).
        """

        if search_string:
            try:
                if self.config.case_sensitive == 0:
                    sspat = re.compile(search_string, re.I|re.MULTILINE)
                else:
                    sspat = re.compile(search_string,re.MULTILINE)
            except re.error:
                sspat = None

        else:
            sspat = None

        filtered_notes = []
        # total number of notes, excluding deleted ones
        active_notes = 0
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
                    # this used to use a filter(), but that would by definition
                    # test all elements, whereas we can stop when the first
                    # matching element is found
                    # now I'm using this awesome trick by Alex Martelli on
                    # http://stackoverflow.com/a/2748753/532513
                    # first parameter of next is a generator
                    # next() executes one step, but due to the if, this will
                    # either be first matching element or None (second param)
                    if t and next((ti for ti in t if sspat.search(ti)), None) is not None:
                        # we have to store our local key also
                        filtered_notes.append(utils.KeyValueObject(key=k, note=n, tagfound=1))

                    elif sspat.search(c):
                        # we have to store our local key also
                        filtered_notes.append(utils.KeyValueObject(key=k, note=n, tagfound=0))

                else:
                    # we have to store our local key also
                    filtered_notes.append(utils.KeyValueObject(key=k, note=n, tagfound=0))
            else:
                if (not sspat or sspat.search(c)):
                    # we have to store our local key also
                    filtered_notes.append(utils.KeyValueObject(key=k, note=n, tagfound=0))

        match_regexp = search_string if sspat else ''

        return filtered_notes, match_regexp, active_notes

    def get_note(self, key):
        return self.notes[key]

    def get_note_content(self, key):
        return self.notes[key].get('content')

    def get_note_status(self, key):
        n = self.notes[key]
        o = utils.KeyValueObject(saved=False, synced=False, modified=False)
        modifydate = float(n['modifydate'])
        savedate = float(n['savedate'])

        if savedate > modifydate:
            o.saved = True
        else:
            o.modified = True

        if float(n['syncdate']) > modifydate:
            o.synced = True

        return o

    def get_save_queue_len(self):
        return self.q_save.qsize()


    def get_sync_queue_len(self):
        return self.q_sync.qsize()

    def helper_key_to_fname(self, k):
            return os.path.join(self.db_path, k) + '.json'

    def helper_save_note(self, k, note):
        """Save a single note to disc.

        """

        if self.config.notes_as_txt:
            t = utils.get_note_title_file(note)
            if t and not note.get('deleted'):
                if k in self.titlelist:
                    logging.debug('Writing note : %s %s' % (t,self.titlelist[k] ))
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
                    with codecs.open(fn, mode='wb', encoding='utf-8') as f:
                        c = note.get('content')
                        if isinstance(c, str):
                            c = unicode(c, 'utf-8')
                        else:
                            c = unicode(c)

                        f.write(c)
                except IOError, e:
                    logging.error('NotesDB_save: Error opening %s: %s' % (fn, str(e)))
                    raise WriteError ('Error opening note file')

                except ValueError, e:
                    logging.error('NotesDB_save: Error writing %s: %s' % (fn, str(e)))
                    raise WriteError ('Error writing note file')

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
            json.dump(note, open(fn, 'wb'), indent=2)

        # record that we saved this to disc.
        note['savedate'] = time.time()

    def sync_note_unthreaded(self, k):
        """Sync a single note with the server.

        Update existing note in memory with the returned data.
        This is a sychronous (blocking) call.
        """

        note = self.notes[k]

        if not note.get('key') or float(note.get('modifydate')) > float(note.get('syncdate')):
            # if has no key, or it has been modified sync last sync,
            # update to server
            uret = self.simplenote.update_note(note)

            if uret[1] == 0:
                # success!
                n = uret[0]

                # if content was unchanged, there'll be no content sent back!
                if n.get('content', None):
                    new_content = True

                else:
                    new_content = False

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

                if int(n.get('syncnum')) > int(note.get('syncnum')):
                    n['syncdate'] = time.time()
                    note.update(n)
                    return (k, True)

                else:
                    return (k, False)

            else:
                return None


    def save_threaded(self):
        for k,n in self.notes.items():
            savedate = float(n.get('savedate'))
            if float(n.get('modifydate')) > savedate or \
               float(n.get('syncdate')) > savedate:
                cn = copy.deepcopy(n)
                # put it on my queue as a save
                o = utils.KeyValueObject(action=ACTION_SAVE, key=k, note=cn)
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
                self.notify_observers('change:note-status', utils.KeyValueObject(what='savedate',key=o.key))
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

        now = time.time()
        for k,n in self.notes.items():
            # if note has been modified sinc the sync, we need to sync.
            # only do so if note hasn't been touched for 3 seconds
            # and if this note isn't still in the queue to be processed by the
            # worker (this last one very important)
            modifydate = float(n.get('modifydate', -1))
            syncdate = float(n.get('syncdate', -1))
            if modifydate > syncdate and \
               now - modifydate > lastmod and \
               k not in self.threaded_syncing_keys:
                # record that we've requested a sync on this note,
                # so that we don't keep on putting stuff on the queue.
                self.threaded_syncing_keys[k] = True
                cn = copy.deepcopy(n)
                # we store the timestamp when this copy was made as the syncdate
                cn['syncdate'] = time.time()
                # put it on my queue as a sync
                o = utils.KeyValueObject(action=ACTION_SYNC_PARTIAL_TO_SERVER, key=k, note=cn)
                self.q_sync.put(o)

        # in this same call, we read out the result queue
        nsynced = 0
        nerrored = 0
        something_in_queue = True
        while something_in_queue:
            try:
                o = self.q_sync_res.get_nowait()

            except Empty:
                something_in_queue = False

            else:
                okey = o.key

                if o.error:
                    nerrored += 1

                else:
                    # o (.action, .key, .note) is something that was synced

                    # we only apply the changes if the syncdate is newer than
                    # what we already have, since the main thread could be
                    # running a full sync whilst the worker thread is putting
                    # results in the queue.
                    if float(o.note['syncdate']) > float(self.notes[okey]['syncdate']):

                        if float(o.note['syncdate']) > float(self.notes[okey]['modifydate']):
                            # note was synced AFTER the last modification to our local version
                            # do an in-place update of the existing note
                            # this could be with or without new content.
                            old_note = copy.deepcopy(self.notes[okey])
                            self.notes[okey].update(o.note)
                            # notify anyone (probably nvPY) that this note has been changed
                            self.notify_observers('synced:note', utils.KeyValueObject(lkey=okey, old_note=old_note))

                        else:
                            # the user has changed stuff since the version that got synced
                            # just record syncnum and version that we got from simplenote
                            # if we don't do this, merging problems start happening.
                            # VERY importantly: also store the key. It
                            # could be that we've just created the
                            # note, but that the user continued
                            # typing. We need to store the new server
                            # key, else we'll keep on sending new
                            # notes.
                            tkeys = ['syncnum', 'version', 'syncdate', 'key']
                            for tk in tkeys:
                                self.notes[okey][tk] = o.note[tk]

                        nsynced += 1
                        self.notify_observers('change:note-status', utils.KeyValueObject(what='syncdate',key=okey))

                # after having handled the note that just came back,
                # we can take it from this blocker dict
                del self.threaded_syncing_keys[okey]

        return (nsynced, nerrored)


    def sync_full(self):
        """Perform a full bi-directional sync with server.

        This follows the recipe in the SimpleNote 2.0 API documentation.
        After this, it could be that local keys have been changed, so
        reset any views that you might have.
        """

        local_updates = {}
        local_deletes = {}
        now = time.time()

        self.notify_observers('progress:sync_full', utils.KeyValueObject(msg='Starting full sync.'))
        # 1. go through local notes, if anything changed or new, update to server
        for ni,lk in enumerate(self.notes.keys()):
            n = self.notes[lk]
            if not n.get('key') or float(n.get('modifydate')) > float(n.get('syncdate')):
                uret = self.simplenote.update_note(n)
                if uret[1] == 0:
                    # replace n with uret[0]
                    # if this was a new note, our local key is not valid anymore
                    del self.notes[lk]
                    # in either case (new or existing note), save note at assigned key
                    k = uret[0].get('key')
                    # we merge the note we got back (content coud be empty!)
                    n.update(uret[0])
                    # and put it at the new key slot
                    self.notes[k] = n

                    # record that we just synced
                    uret[0]['syncdate'] = now

                    # whatever the case may be, k is now updated
                    local_updates[k] = True
                    if lk != k:
                        # if lk was a different (purely local) key, should be deleted
                        local_deletes[lk] = True

                    self.notify_observers('progress:sync_full', utils.KeyValueObject(msg='Synced modified note %d to server.' % (ni,)))

                else:
                    raise SyncError("Sync step 1 error - Could not update note to server")

        # 2. if remote syncnum > local syncnum, update our note; if key is new, add note to local.
        # this gets the FULL note list, even if multiple gets are required
        self.notify_observers('progress:sync_full', utils.KeyValueObject(msg='Retrieving full note list from server, could take a while.'))
        nl = self.simplenote.get_note_list()
        if nl[1] == 0:
            nl = nl[0]
            self.notify_observers('progress:sync_full', utils.KeyValueObject(msg='Retrieved full note list from server.'))

        else:
            raise SyncError('Could not get note list from server.')

        server_keys = {}
        lennl = len(nl)
        sync_from_server_errors = 0
        for ni,n in enumerate(nl):
            k = n.get('key')
            server_keys[k] = True
            # this works, only because in phase 1 we rewrite local keys to
            # server keys when we get an updated not back from the server
            if k in self.notes:
                # we already have this
                # check if server n has a newer syncnum than mine
                if int(n.get('syncnum')) > int(self.notes[k].get('syncnum', -1)):
                    # and the server is newer
                    ret = self.simplenote.get_note(k)
                    if ret[1] == 0:
                        self.notes[k].update(ret[0])
                        local_updates[k] = True
                        # in both cases, new or newer note, syncdate is now.
                        self.notes[k]['syncdate'] = now
                        self.notify_observers('progress:sync_full', utils.KeyValueObject(msg='Synced newer note %d (%d) from server.' % (ni,lennl)))

                    else:
                        logging.error('Error syncing newer note %s from server: %s' % (k, ret[0]))
                        sync_from_server_errors+=1

            else:
                # new note
                ret = self.simplenote.get_note(k)
                if ret[1] == 0:
                    self.notes[k] = ret[0]
                    local_updates[k] = True
                    # in both cases, new or newer note, syncdate is now.
                    self.notes[k]['syncdate'] = now
                    self.notify_observers('progress:sync_full', utils.KeyValueObject(msg='Synced new note %d (%d) from server.' % (ni,lennl)))

                else:
                    logging.error('Error syncing new note %s from server: %s' % (k, ret[0]))
                    sync_from_server_errors+=1

        # 3. for each local note not in server index, remove.
        for lk in self.notes.keys():
            if lk not in server_keys:
                if self.config.notes_as_txt:
                    tfn = os.path.join(self.config.txt_path, utils.get_note_title_file(self.notes[lk]))
                    if os.path.isfile(tfn):
                        os.unlink(tfn)
                del self.notes[lk]
                local_deletes[lk] = True

        # sync done, now write changes to db_path
        for uk in local_updates.keys():
            try:
                self.helper_save_note(uk, self.notes[uk])

            except WriteError, e:
                raise WriteError(e)

        for dk in local_deletes.keys():
            fn = self.helper_key_to_fname(dk)
            if os.path.exists(fn):
                os.unlink(fn)

        self.notify_observers('progress:sync_full', utils.KeyValueObject(msg='Full sync complete.'))

        return sync_from_server_errors

    def set_note_content(self, key, content):
        n = self.notes[key]
        old_content = n.get('content')
        if content != old_content:
            n['content'] = content
            n['modifydate'] = time.time()
            self.notify_observers('change:note-status', utils.KeyValueObject(what='modifydate', key=key))

    def set_note_tags(self, key, tags):
        n = self.notes[key]
        old_tags = n.get('tags')
        tags = utils.sanitise_tags(tags)
        if tags != old_tags:
            n['tags'] = tags
            n['modifydate'] = time.time()
            self.notify_observers('change:note-status', utils.KeyValueObject(what='modifydate', key=key))

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
            self.notify_observers('change:note-status', utils.KeyValueObject(what='modifydate', key=key))


    def worker_save(self):
        while True:
            o = self.q_save.get()

            if o.action == ACTION_SAVE:
                # this will write the savedate into o.note
                # with filename o.key.json
                try:
                    self.helper_save_note(o.key, o.note)

                except WriteError, e:
                    logging.error('FATAL ERROR in access to file system')
                    print "FATAL ERROR: Check the nvpy.log"
                    os._exit(1)

                else:
                    # put the whole thing back into the result q
                    # now we don't have to copy, because this thread
                    # is never going to use o again.
                    # somebody has to read out the queue...
                    self.q_save_res.put(o)

    def worker_sync(self):
        while True:
            o = self.q_sync.get()

            if o.action == ACTION_SYNC_PARTIAL_TO_SERVER:
                self.waiting_for_simplenote = True
                if 'key' in o.note:
                    logging.debug('Updating note %s (local key %s) to server.' % (o.note['key'], o.key))

                else:
                    logging.debug('Sending new note (local key %s) to server.' % (o.key,))

                uret = self.simplenote.update_note(o.note)
                self.waiting_for_simplenote = False

                if uret[1] == 0:
                    # success!
                    n = uret[0]

                    if not n.get('content', None):
                        # if note has not been changed, we don't get content back
                        # delete our own copy too.
                        del o.note['content']

                    logging.debug('Server replies with updated note ' + n['key'])

                    # syncdate was set when the note was copied into our queue
                    # we rely on that to determine when a returned note should
                    # overwrite a note in the main list.

                    # store the actual note back into o
                    # in-place update of our existing note copy
                    o.note.update(n)

                    # success!
                    o.error = 0

                    # and put it on the result queue
                    self.q_sync_res.put(o)

                else:
                    o.error = 1
                    self.q_sync_res.put(o)
