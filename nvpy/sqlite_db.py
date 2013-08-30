# nvPY: cross-platform note-taking app with simplenote syncing
# copyright 2012 by Charl P. Botha <cpbotha@vxlabs.com>
# new BSD license

import os
import re
import time
from notes_db import SyncError, ReadError, WriteError

from threading import Thread
import time
import utils

import sqlite3

class SqliteDB(utils.SubjectMixin):
    """SqliteDb is an alternative backend for notes' storage, based on sqlite
    """
    
    def _helper_check_table_existence(self, table_name):
        if [x for x in self.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", [table_name])]:
            return True
        else:
            return False

    
    def __init__(self, config):
        # Compatibility stuff
        utils.SubjectMixin.__init__(self)
        self.waiting_for_simplenote = 0
    
        self.config = config
        # TODO separate path for sqlite?
        self.db_path = os.path.join(self.config.db_path , "nvpy.db")
        # FIXME Allow for changes in the schema
        self.table = "nvpy_notes_v1"
        
        # Check if the database already exists
        if os.path.exists(self.db_path):
            newfile = True
        else:
            newfile = False
        
        self.db = sqlite3.connect(self.db_path)
        self.db.row_factory = sqlite3.Row
        
        # Create the database from scratch if it doesn't exist. Avoid adding tables to an existing not-nvpy database
        # FIXME Use a different table for tags, and a tags-notes table for the many to many relationship
        # FIXME Don't create a reverse index for *all* columns, just for 'content' [and maybe 'tags']
        if not self._helper_check_table_existence(self.table) and not newfile:
            self.db.execute("CREATE VIRTUAL TABLE nvpy_notes_v1 USING fts3(content, createdate, modifydate, pinned, t)") # t means tags
        elif self._helper_check_table_existence(self.table) and not newfile:
            raise ReadError
        
    def get_note_count(self):
        with self.db:
            cur = self.db.execute("SELECT count(*) FROM nvpy_notes_v1;")
            count = cur.fetchone()[0]
            return count

    def create_note(self, title):
        now = int(time.time())
        self.db.execute("INSERT INTO nvpy_notes_v1 VALUES (?, ?, ?, 0, '')", [title, now, now])
        
        with self.db:
            cur = self.db.execute("SELECT last_insert_rowid();")
            rowid = cur.fetchone()[0]
            return str(rowid)

    def delete_note(self, key):
        self.db.execute("DELETE FROM nvpy_notes_v1 WHERE rowid=?", [int(key)])

    def filter_notes(self, search_string=''):
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
        return self.filter_notes_gstyle(search_string)


    def filter_notes_gstyle(self, search_string=''):
        # TODO sorting
        if search_string:
            search_string_star = search_string + '*'
            notes_raw = (n for n in self.db.execute("SELECT rowid, * FROM nvpy_notes_v1 WHERE content MATCH ?", [search_string_star]))
        else:
            notes_raw = (n for n in self.db.execute("SELECT rowid, * FROM nvpy_notes_v1"))
        # FIXME handle tags
        # FIXME handle row to dict conversion in an helper
        notes = [utils.KeyValueObject(key = n["rowid"], note = {
                    'content' : n["content"],
                    'modifydate' : n["modifydate"],
                    'createdate' : n["createdate"],
                    'savedate' : 0, # never been written to disc
                    'syncdate' : 0, # never been synced with server
                    'tags' : n["t"].split(",")
                }, tagfound = 0) for n in notes_raw]
        active_notes = len(notes)
        
        # Calculate a regex from the search string
        words = [re.sub(r"""\"|\'""", '', w) for w in re.findall("""([^"' ]+|\"[^\"]+\"|\'[^']+\')""", search_string)]
        
        return notes, "|".join(words), active_notes

    def filter_notes_regexp(self, search_string=''):
        """Return list of notes filtered with search_string, 
        a regular expression, each a tuple with (local_key, note). 
        """
        # TODO implement
        pass

    def get_note(self, key):
        with self.db:
            cur = self.db.execute("SELECT * FROM nvpy_notes_v1 WHERE rowid=?", [int(key)])
            results = cur.fetchone()
            return {
                    'content' : results["content"],
                    'modifydate' : results["modifydate"],
                    'createdate' : results["createdate"],
                    'savedate' : 0, # never been written to disc
                    'syncdate' : 0, # never been synced with server
                    'tags' : results["t"].split(",")
                }

    def get_note_content(self, key):
        with self.db:
            cur = self.db.execute("SELECT * FROM nvpy_notes_v1 WHERE rowid=?", [int(key)])
            content = cur.fetchone()["content"]
            return content
    
    def get_note_status(self, key):
        # FIXME bogus
        return utils.KeyValueObject(saved=False, synced=False, modified=False)

    def set_note_content(self, key, content):
        now = int(time.time())
        self.db.execute("UPDATE nvpy_notes_v1 SET content=?, modifydate=? WHERE rowid=?", [content, now, int(key)])

    def set_note_tags(self, key, tags):
        now = int(time.time())
        tags = utils.sanitise_tags(tags)
        # FIXME tags are an hack
        tags_string = ",".join(tags)
        self.db.execute("UPDATE nvpy_notes_v1 SET t=?, modifydate=? WHERE rowid=?", [tags_string, now, int(key)])

    def set_note_pinned(self, key, pinned):
        now = int(time.time())
        if pinned:
            self.db.execute("UPDATE nvpy_notes_v1 SET pinned=1, modifydate=? WHERE rowid=?", [now, int(key)])
        else:
            self.db.execute("UPDATE nvpy_notes_v1 SET pinned=0, modifydate=? WHERE rowid=?", [now, int(key)])

    # Saving and syncing stuff. TODO implement, TODO: See if it can be moved to other classes
    def get_save_queue_len(self):
        return 0
            
    def get_sync_queue_len(self):
        return 0

        
    def sync_note_unthreaded(self, k):
        """Sync a single note with the server.

        Update existing note in memory with the returned data.  
        This is a sychronous (blocking) call.
        """
        return None

        
    def save_threaded(self):
        return 0
    
    def sync_to_server_threaded(self, wait_for_idle=True):
        """Only sync notes that have been changed / created locally since previous sync.
        
        This function is called by the housekeeping handler, so once every
        few seconds.
        
        @param wait_for_idle: Usually, last modification date has to be more
        than a few seconds ago before a sync to server is attempted. If
        wait_for_idle is set to False, no waiting is applied. Used by exit
        cleanup in controller.
        
        """
        return (0, 0)
    
    
    def sync_full(self):
        """Perform a full bi-directional sync with server.
        
        This follows the recipe in the SimpleNote 2.0 API documentation.
        After this, it could be that local keys have been changed, so
        reset any views that you might have.
        """
        return 0
        

