# nvPY: cross-platform note-taking app with simplenote syncing
# copyright 2012 by Charl P. Botha <cpbotha@vxlabs.com>
# new BSD license

import copy
import glob
import os
import json
from Queue import Queue, Empty
import re
from simplenote import Simplenote
from threading import Thread
import time
import utils

ACTION_SAVE = 0
ACTION_SYNC = 1

class NotesDB(utils.SubjectMixin):
    """NotesDB will take care of the local notes database and syncing with SN.
    """
    def __init__(self, db_path, sn_username, sn_password):
        utils.SubjectMixin.__init__(self)
        # create db dir if it does not exist
        if not os.path.exists(db_path):
            os.mkdir(db_path)
            
        self.db_path = db_path
        
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
        self.simplenote = Simplenote(sn_username, sn_password)
        
        # try to do a full sync before we start.
        try:
            self.sync_full()
        except RuntimeError:
            pass
        
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
        
    def filter_notes(self, search_string=None):
        """Return list of notes filtered with search_string, 
        a regular expression, each a tuple with (local_key, note). 
        """

        filtered_notes = []
        for k in self.notes:
            n = self.notes[k]
            c = n.get('content')
            if not n.get('deleted') and (not search_string or re.search(search_string, c)):
                # we have to store our local key also
                filtered_notes.append(utils.KeyValueObject(key=k, note=n))
            
        # sort alphabetically on title
        filtered_notes.sort(key=lambda o: utils.get_note_title(o.note))
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
            
    
    def helper_key_to_fname(self, k):
        return os.path.join(self.db_path, k) + '.json'
    
    def helper_save_note(self, k, note):
        """Save a single note to disc.
        
        """
        
        # simplenote key in note gets precedence when saving.
        sk = note.get('key')
        if sk:
            k = sk
            
        fn = self.helper_key_to_fname(k)
        json.dump(note, open(fn, 'wb'), indent=2)
        # record that we saved this to disc.
        note['savedate'] = time.time()
        
    def helper_sync_note(self, k, note):
        """Sync a single note with the server.
        
        This is a sychronous (blocking) call.
        """
        uret = self.simplenote.update_note(note)
        if uret[1] == 0:
            # success!
            n = uret[0]
            # if content was unchanged, there'll be no content sent back!
            # so we have to copy our old content
            if not n.get('content', None):
                n['content'] = note['content']
                # FIXME: record that content has not changed
                # then we know GUI does not have to be updated either.
                
            if n.get('key') != k:
                # new key assigned during sync
                # for now we keep the old local key around ONLY AS IN-MEM INDEX
                # 1. remove from filesystem
                os.unlink(self.helper_key_to_fname(k))
                
            now = time.time()
            # 1. store when we've synced
            n['syncdate'] = now
            
            # update our existing note in-place!
            self.notes[k].update(n)
            # return the key
            return k
            
        else:
            return None
        
        
    def save_unthreaded(self):
        """Write all notes that have been changed since last save to disc.
        
        This is usually called every few seconds by nvPY, so it should be quick.
        """
        nsaved = 0
        for k,n in self.notes.items():
            if float(n.get('modifydate')) > float(n.get('savedate')):
                # helper_save_note will pick simplenote key if available, else localkey
                self.helper_save_note(k, n)
                nsaved += 1
                
        return nsaved
    
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
        
    
    def sync_to_server_unthreaded(self):
        """Only sync notes that have been changed / created locally since previous sync.
        
        This is a fully blocking non-threaded call.
        """
        
        nsynced = 0
        nerrored = 0
        for k,n in self.notes.items():
            # if note has been modified sinc the sync, we need to sync. doh.
            if float(n.get('modifydate')) > float(n.get('syncdate')):
                # helper sets syncdate
                # also updates our note in-place if anything comes back
                k = self.helper_sync_note(k,n)
                
                if k:
                    n = self.notes[k]
                    nsynced += 1
                    # this will set syncdate and modifydate = now
                    self.helper_save_note(k, n)
                    
                else:
                    nerrored += 1
                
        return (nsynced, nerrored)
    
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
            if modifydate > float(n.get('syncdate', -1)) and \
               now - modifydate > 3 and \
               k not in self.threaded_syncing_keys:
                self.threaded_syncing_keys[k] = True
                print 'SST key', k, 'mod-date', n.get('modifydate'), 'syncdate', n.get('syncdate')
                # FIXME: record that we've requested a sync on this note,
                # so that we don't keep on putting stuff on the queue.
                cn = copy.deepcopy(n)
                # we store the timestamp when this copy was made as the syncdate
                cn['syncdate'] = time.time()
                # put it on my queue as a sync
                o = utils.KeyValueObject(action=ACTION_SYNC, key=k, note=cn)
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
                    # -- the key could have changed (first sync)
                    # -- we have to record the syncdate + modifydate
                    nkey = o.note['key']
                    
                    if float(o.note['syncdate']) > float(self.notes[okey]['modifydate']):
                        # note was synced AFTER the last modification to our local version
                        # do an in-place update of the existing note
                        # this could be with or without new content.
                        self.notes[okey].update(o.note)
                        # notify anyone (probably nvPY) that this note has been changed
                        self.notify_observers('synced:note', utils.KeyValueObject(lkey=okey))
                        
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
        local_updates = {}
        local_deletes = {}
        now = time.time()

        print "step 1"
        # 1. go through local notes, if anything changed or new, update to server
        for lk in self.notes.keys():
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
                    
                    # just synced, and of course note could be modified, so record.
                    uret[0]['syncdate'] = now
                    
                    # whatever the case may be, k is now updated
                    local_updates[k] = True
                    if lk != k:
                        # if lk was a different (purely local) key, should be deleted
                        local_deletes[lk] = True
             
        print "step 2"
        # 2. if remote syncnum > local syncnum, update our note; if key is new, add note to local.
        # this gets the FULL note list, even if multiple gets are required       
        nl = self.simplenote.get_note_list()
        if nl[1] == 0:
            nl = nl[0]
            
        else:
            raise RuntimeError('Could not get note list from server.')
        
        print "  got note list."
            
        server_keys = {}
        for n in nl:
            k = n.get('key')
            server_keys[k] = True
            if k in self.notes:
                # we already have this
                # check if server n has a newer syncnum than mine
                if int(n.get('syncnum')) > int(self.notes[k].get('syncnum', -1)):
                    # and the server is newer
                    print "  getting newer note", k
                    ret = self.simplenote.get_note(k)
                    if ret[1] == 0:
                        self.notes[k].update(ret[0])
                        local_updates[k] = True
                        
            else:
                # new note
                print "  getting new note", k
                ret = self.simplenote.get_note(k)
                if ret[1] == 0:
                    self.notes[k] = ret[0]
                    local_updates[k] = True
                    
            # in both cases, new or newer note, syncdate is now.
            self.notes[k]['syncdate'] = now
                    
            
                     
        print "step 3"
        # 3. for each local note not in server index, remove.     
        for lk in self.notes.keys():
            if lk not in server_keys:
                del self.notes[lk]
                local_deletes[lk] = True
                
        # sync done, now write changes to db_path
        for uk in local_updates.keys():
            self.helper_save_note(uk, self.notes[uk])
            
        for dk in local_deletes.keys():
            os.unlink(self.helper_key_to_fname(dk))
            
        print "done syncin'"
        
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
                self.helper_save_note(o.key, o.note)
                
                # put the whole thing back into the result q
                # now we don't have to copy, because this thread
                # is never going to use o again.
                # somebody has to read out the queue...
                self.q_save_res.put(o)
                
            elif o.action == ACTION_SYNC:
                uret = self.simplenote.update_note(o.note)
                if uret[1] == 0:
                    # success!
                    n = uret[0]
                    now = time.time()
                    # if content was unchanged, there'll be no content sent back!
                    # so we have to copy our old content
                    if not n.get('content', None):
                        # if note has not been changed, we don't get content back
                        # delete our own copy too.
                        del o.note['content']
                        
                    if n.get('key') != o.key:
                        # new key assigned during sync
                        # for now we keep the old local key around ONLY AS IN-MEM INDEX
                        # but we do have to remove from filesystem
                        os.unlink(self.helper_key_to_fname(o.key))
                        
                    # 1. store when we've synced
                    n['syncdate'] = now
                    
                    # store the actual note back into o
                    # in-place update of our existing note copy
                    o.note.update(n)

                    # success!
                    o.error = 0
                    
                    # and put it on the result queue
                    self.q_sync_res.put(o)
                    print 'WORKER SYNCED syncdate', o.note.get('syncdate')
                    
                else:
                    o.error = 1
