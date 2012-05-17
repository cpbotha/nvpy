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

class NotesDB:
    """NotesDB will take care of the local notes database and syncing with SN.
    """
    def __init__(self, db_path, sn_username, sn_password):
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
            # filename is ALWAYS localkey; only simplenote key when available
            localkey = os.path.splitext(os.path.basename(fn))[0]
            self.notes[localkey] = n
            # we maintain in memory a timestamp of the last save
            # these notes have just been read, so at this moment
            # they're in sync with the disc.
            n['savedate'] = now
        
        # initialise the simplenote instance we're going to use
        # this does not yet need network access
        self.simplenote = Simplenote(sn_username, sn_password)
        
        # first line with non-whitespace should be the title
        self.title_re = re.compile('\s*(.*)\n?')
        
        # save and sync queue
        # we only want ONE thread to do both saving and syncing
        self.q_ss = Queue()
        # but separate result queues for saving and syncing
        self.q_save_res = Queue()
        self.q_sync_res = Queue()
        
        thread_ss = Thread(target=self.worker_ss)
        # we want all save + sync calls to finish when the process finishes.
        thread_ss.setDaemon(False)
        thread_ss.start()
        
    def create_note(self, title):
        # need to get a key unique to this database. not really important
        # what it is, as long as it's unique.
        new_key = utils.generate_random_key()
        while new_key in self.notes:
            new_key = utils.generate_random_key()
            
        timestamp = time.time()
            
        new_note = {'key' : new_key,
                    'content' : title,
                    'modifydate' : timestamp,
                    'createdate' : timestamp,
                    'savedate' : 0, # never been written to disc
                    'syncdate' : 0 # never been synced with server
                    }
        
        self.notes[new_key] = new_note
        
        return new_key
        
    def get_note_names(self, search_string=None):
        """Return 
        """

        note_names = []
        for k in self.notes:
            n = self.notes[k]
            c = n.get('content')
            tmo = self.title_re.match(c)
            if tmo and (not search_string or re.search(search_string, c)):
                title = tmo.groups()[0]
                
                # timestamp
                # convert to datetime with datetime.datetime.fromtimestamp(modified)
                modified = float(n.get('modifydate'))

                o = utils.KeyValueObject(key=k, title=title, modified=modified)
                note_names.append(o)
            
        # sort alphabetically on title
        note_names.sort(key=lambda o: o.title)
        return note_names
    
    def get_note_content(self, key):
        return self.notes[key].get('content')
    
    def helper_key_to_fname(self, k):
        return os.path.join(self.db_path, k) + '.json'
    
    def helper_save_note(self, k, note):
        """Save a single note to disc.
        """
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
                # 1. delete from our notes list
                del self.notes[k]
                # 2. remove from filesystem
                os.unlink(self.helper_key_to_fname(k))
                # set us up with new key
                k = n.get('key')
                
            now = time.time()
            # 1. store when we've synced
            # 2. also store that note is modified (so it'll be written to disc) 
            n['modifydate'] = n['syncdate'] = now
            
            # store the new n at k, possibly new
            self.notes[k] = n
            # return the key
            return k
            
        else:
            return None
        
        
    def save(self):
        """Write all notes that have been changed since last save to disc.
        
        This is usually called every few seconds by nvPY, so it should be quick.
        """
        nsaved = 0
        for k,n in self.notes.items():
            if float(n.get('modifydate')) > float(n.get('savedate')):
                self.helper_save_note(k, n)
                nsaved += 1
                
        return nsaved
    
    def save_threaded(self):
        for k,n in self.notes.items():
            if float(n.get('modifydate')) > float(n.get('savedate')):
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
                # o (.action, .key, .note) is somethig that was written to disk
                # we only record the savedate.
                self.notes[o.key]['savedate'] = o.note['savedate']
                nsaved += 1
                
        return nsaved
        
    
    def sync_to_server(self):
        """Only sync notes that have been changed / created locally since previous sync.
        """
        
        nsynced = 0
        nerrored = 0
        for k,n in self.notes.items():
            # if note has been modified sinc the sync, we need to sync. doh.
            if float(n.get('modifydate')) > float(n.get('syncdate')):
                # helper sets syncdate
                k = self.helper_sync_note(k,n)
                
                if k:
                    n = self.notes[k]
                    nsynced += 1
                    # this will set syncdate and modifydate = now
                    self.helper_save_note(k, n)
                    
                else:
                    nerrored += 1
                
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
                    self.notes[k] = uret[0]
                    
                    # just synced, and of course note could be modified, so record.
                    uret[0]['syncdate'] = uret[0]['modifydate'] = now
                    
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
                        self.notes[k] = ret[0]
                        local_updates[k] = True
                        ret[0]['syncdate'] = ret[0]['modifydate'] = now
                        
            else:
                # new note
                print "  getting new note", k
                ret = self.simplenote.get_note(k)
                if ret[1] == 0:
                    self.notes[k] = ret[0]
                    local_updates[k] = True
                    ret[0]['syncdate'] = ret[0]['modifydate'] = now
                     
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
