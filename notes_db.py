import glob
import os
import json
import re
from simplenote import Simplenote

class NotesDB:
    """NotesDB will take care of the local notes database and syncing with SN.
    """
    def __init__(self, db_path, sn_username, sn_password):
        # create db dir if it does not exist
        if not os.path.exists(db_path):
            os.mkdir(db_path)
            
        self.db_path = db_path
            
        # now read all .json files from disk
        fnlist = glob.glob(self.helper_key_to_fname('*'))
        self.notes = {}
        for fn in fnlist:
            n = json.load(open(fn, 'rb'))
            # filename is ALWAYS localkey; only simplenote key when available
            localkey = os.path.splitext(os.path.basename(fn))[0]
            self.notes[localkey] = n
            
        
        # initialise the simplenote instance we're going to use
        # this does not yet need network access
        self.simplenote = Simplenote(sn_username, sn_password)
        
        self.fl_re = re.compile('^(.*)\n')
        
    def get_note_names(self):
        """Return 
        """
        
        note_names = []
        for k in self.notes:
            n = self.notes[k]
            c = n.get('content')
            tmo = self.fl_re.match(c)
            if tmo:
                title = tmo.groups()[0]
                
                # timestamp
                # convert to datetime with datetime.datetime.fromtimestamp(modified)
                modified = float(n.get('modifydate'))
                
                note_names.append((k, title, modified))
            
        # we could sort note_names here
        return note_names
    
    def get_note_content(self, key):
        return self.notes[key].get('content')

    def helper_key_to_fname(self, k):
        return os.path.join(self.db_path, k) + '.json'
    
    def helper_save_note(self, k, note):
        fn = self.helper_key_to_fname(k)
        json.dump(note, open(fn, 'wb'), indent=2)
    
    def sync_full(self):
        local_updates = {}
        local_deletes = {}

        print "step 1"
        # 1. go through local notes, if anything changed or new, update to server
        for lk in self.notes.keys():
            n = self.notes[lk]
            if not n.get('key') or n.get('localtouch'):
                uret = self.simplenote.update_note(n)
                if uret[1] == 0:
                    # replace n with uret[0]
                    # if this was a new note, our local key is not valid anymore
                    del self.notes[lk]
                    # in either case (new or existing note), save note at assigned key
                    k = uret[0].get('key')
                    self.notes[k] = uret[0]
                    
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
                if n.get('syncnum') > self.notes[k]:
                    # and the server is newer
                    print "  getting newer note", k
                    ret = self.simplenote.get_note(k)
                    if ret[1] == 0:
                        self.notes[k] = ret[0]
                        local_updates[k] = True
                        
            else:
                # new note
                print "  getting new note", k
                ret = self.simplenote.get_note(k)
                if ret[1] == 0:
                    self.notes[k] = ret[0]
                    local_updates[k] = True
                     
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
        
        
    def do_full_get(self):
        # this returns a tuple ([], -1) if wrong password
        # on success, ([docs], 0)
        # each doc:
        #{u'createdate': u'1335860754.841000',
        # u'deleted': 0,
        # u'key': u'455f66ee936711e19657591a71011082',
        # u'minversion': 10,
        # u'modifydate': u'1337007469.836000',
        # u'syncnum': 54,
        # u'systemtags': [],
        # u'tags': [],
        # u'version': 40}
        
        # FIXME: this will only return 100 notes at a time if I can believe the documentation :(        
        note_list = self.simplenote.get_note_list()
        
        # simplenote.get_note(key) returns (doc, status)
        # where doc is all of the above with extra field content

        server_notes = []        
        if note_list[1] == 0:
            for i in note_list[0]:
                n = self.simplenote.get_note(i.get('key'))
                if n[1] == 0:
                    server_notes.append(n[0])
                    
        # write server_notes to disc
        for n in server_notes:
            f = open(os.path.join(self.db_path, n.get('key')) + '.json', 'wb')
            json.dump(n, f, indent=2)

