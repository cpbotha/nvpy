# nvPY: cross-platform note-taking app with simplenote syncing
# copyright 2012 by Charl P. Botha <cpbotha@vxlabs.com>
# new BSD license

import copy
import glob
import os
import json
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
        
        now = time.time()    
        # now read all .json files from disk
        fnlist = glob.glob(self.helper_key_to_fname('*'))
        self.notes = {}
        for fn in fnlist:
            n = json.load(open(fn, 'rb'))
            # we always have a localkey, also when we don't have a note['key'] yet (no sync)
            localkey = os.path.splitext(os.path.basename(fn))[0]
            self.notes[localkey] = n
            # we maintain in memory a timestamp of the last save
            # these notes have just been read, so at this moment
            # they're in sync with the disc.
            n['savedate'] = now
        
        # initialise the simplenote instance we're going to use
        # this does not yet need network access
        self.simplenote = Simplenote(config.sn_username, config.sn_password)
        
        # we'll use this to store which notes are currently being synced by
        # the background thread, so we don't add them anew if they're still
        # in progress
        self.threaded_syncing_keys = {}
        
        # save and sync queue
        # we only want ONE thread to do both saving and syncing
        self.q_ss = Queue()
        # but separate result queues for saving and syncing
        self.q_save_res = Queue()
        self.q_sync_res = Queue()
        
        thread_ss = Thread(target=self.worker_ss)
        thread_ss.setDaemon(True)
        thread_ss.start()
        
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
                    'syncdate' : 0 # never been synced with server
                    }
        
        self.notes[new_key] = new_note
        
        return new_key
    
    def delete_note(self, key):
        n = self.notes[key]
        n['deleted'] = 1
        n['modifydate'] = time.time()
        
    def filter_notes(self, search_string=None):
        """Return list of notes filtered with search_string, 
        a regular expression, each a tuple with (local_key, note). 
        """

        if search_string:
            try:
                sspat = re.compile(search_string)
            except re.error:
                sspat = None
            
        else:
            sspat = None

        filtered_notes = []
        for k in self.notes:
            n = self.notes[k]
            c = n.get('content')
            if not n.get('deleted') and (not sspat or sspat.search(c)):
                # we have to store our local key also
                filtered_notes.append(utils.KeyValueObject(key=k, note=n))
            
        if self.config.sort_mode == 0:
            # sort alphabetically on title
            filtered_notes.sort(key=lambda o: utils.get_note_title(o.note))
            
        else:
            # last modified on top
            filtered_notes.sort(key=lambda o: -float(o.note.get('modifydate', 0)))
            
        return filtered_notes
    
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
            
    def get_ss_queue_len(self):
        return self.q_ss.qsize()
        
    def helper_key_to_fname(self, k):
        return os.path.join(self.db_path, k) + '.json'
    
    def helper_save_note(self, k, note):
        """Save a single note to disc.
        
        """
        
        fn = self.helper_key_to_fname(k)
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
                self.q_ss.put(o)
                
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
        
    
    def sync_to_server_threaded(self):
        """Only sync notes that have been changed / created locally since previous sync.
        
        """
        
        now = time.time()
        for k,n in self.notes.items():
            # if note has been modified sinc the sync, we need to sync.
            # only do so if note hasn't been touched for 3 seconds
            # and if this note isn't still in the queue to be processed by the
            # worker (this last one very important)
            modifydate = float(n.get('modifydate', -1))
            syncdate = float(n.get('syncdate', -1))
            if modifydate > syncdate and \
               now - modifydate > 3 and \
               k not in self.threaded_syncing_keys:
                # record that we've requested a sync on this note,
                # so that we don't keep on putting stuff on the queue.
                self.threaded_syncing_keys[k] = True
                cn = copy.deepcopy(n)
                # we store the timestamp when this copy was made as the syncdate
                cn['syncdate'] = time.time()
                # put it on my queue as a sync
                o = utils.KeyValueObject(action=ACTION_SYNC_PARTIAL_TO_SERVER, key=k, note=cn)
                self.q_ss.put(o)
                
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
                # this has come back.
                del self.threaded_syncing_keys[okey]

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
                            tkeys = ['syncnum', 'version', 'syncdate']
                            for tk in tkeys:
                                self.notes[okey][tk] = o.note[tk]
                            
                        nsynced += 1
                        self.notify_observers('change:note-status', utils.KeyValueObject(what='syncdate',key=okey))
                    
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
                    raise SyncError("Sync step 1 error: Could not update note to server.")
             
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
        for ni,n in enumerate(nl):
            k = n.get('key')
            server_keys[k] = True
            if k in self.notes:
                # we already have this
                # check if server n has a newer syncnum than mine
                if int(n.get('syncnum')) > int(self.notes[k].get('syncnum', -1)):
                    # and the server is newer
                    ret = self.simplenote.get_note(k)
                    if ret[1] == 0:
                        self.notes[k].update(ret[0])
                        local_updates[k] = True
                        self.notify_observers('progress:sync_full', utils.KeyValueObject(msg='Synced newer note %d (%d) from server.' % (ni,lennl)))
                        
            else:
                # new note
                ret = self.simplenote.get_note(k)
                if ret[1] == 0:
                    self.notes[k] = ret[0]
                    local_updates[k] = True
                    self.notify_observers('progress:sync_full', utils.KeyValueObject(msg='Synced new note %d (%d) from server.' % (ni,lennl)))
                    
            # in both cases, new or newer note, syncdate is now.
            self.notes[k]['syncdate'] = now
                    
        # 3. for each local note not in server index, remove.     
        for lk in self.notes.keys():
            if lk not in server_keys:
                del self.notes[lk]
                local_deletes[lk] = True
                
        # sync done, now write changes to db_path
        for uk in local_updates.keys():
            self.helper_save_note(uk, self.notes[uk])
            
        for dk in local_deletes.keys():
            fn = self.helper_key_to_fname(dk)
            if os.path.exists(fn):
                os.unlink(fn)

        self.notify_observers('progress:sync_full', utils.KeyValueObject(msg='Full sync complete.'))
        
    def set_note_content(self, key, content):
        n = self.notes[key]
        old_content = n.get('content')
        if content != old_content:
            n['content'] = content
            n['modifydate'] = time.time()
            self.notify_observers('change:note-status', utils.KeyValueObject(what='modifydate', key=key))

    def worker_ss(self):
        while True:
            o = self.q_ss.get()
            
            if o.action == ACTION_SAVE:
                # this will write the savedate into o.note
                # with filename o.key.json
                self.helper_save_note(o.key, o.note)
                
                # put the whole thing back into the result q
                # now we don't have to copy, because this thread
                # is never going to use o again.
                # somebody has to read out the queue...
                self.q_save_res.put(o)
                
            elif o.action == ACTION_SYNC_PARTIAL_TO_SERVER:
                uret = self.simplenote.update_note(o.note)
                if uret[1] == 0:
                    # success!
                    n = uret[0]

                    if not n.get('content', None):
                        # if note has not been changed, we don't get content back
                        # delete our own copy too.
                        del o.note['content']
                        
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
                    
                   
