#!/usr/bin/env python

# nvPY: cross-platform note-taking app with simplenote syncing
# copyright 2012 by Charl P. Botha <cpbotha@vxlabs.com>
# new BSD license

# inspired by notational velocity and nvALT, neither of which I've used,
# and ResophNotes, which I have used.

# full width horizontal bar at top to search
# left column with current results: name, mod date, summary, tags
# right column with text of currently selected note

# * typing in the search bar:
# - press enter: focus jumps to note if ANYTHING is selected. if nothing is
# selected, enter creates a new note with the current string as its name.
# - esc clears the search entry, esc again jumps to list
# - up and down changes currently selected list
# * in note conten area
# - esc goes back to notes list.

# http://www.scribd.com/doc/91277952/Simple-Note-API-v2-1-3
# this also has a sync algorithm!

# 1. finish implementing search
# 1.5. think about other storage formats. What if we want to store more? (cursor position and so on. sqlite?)
# 2. note editing
#   a) saving to disc: remember lmodified or whatever.
#   b) syncing with simplenote

# to check if we're online

import codecs
import ConfigParser
from notes_db import NotesDB, SyncError
import os
import sys
import time

from utils import KeyValueObject, SubjectMixin
import view
import webbrowser

try:
    import markdown
except ImportError:
    HAVE_MARKDOWN = False
else:
    HAVE_MARKDOWN = True
    
try:
    import docutils
    import docutils.core
except ImportError:
    HAVE_DOCUTILS = False
else:
    HAVE_DOCUTILS = True

class Config:
    def __init__(self, app_dir):
        """
        @param app_dir: the directory containing nvPY.py
        """
       
        self.app_dir = app_dir
        # cross-platform way of getting home dir!
        # http://stackoverflow.com/a/4028943/532513
        home = os.path.abspath(os.path.expanduser('~'))
        defaults = {'app_dir' : app_dir,
                    'appdir' : app_dir,
                    'home' : home,
                    'housekeeping_interval' : '2',
                    'sort_mode' : '1',
                    'db_path' : os.path.join(home, '.nvpy'),
                    'font_family' : 'Courier',
                    'font_size' : '12'
                   }
        
        # allow_no_value=True means we'll just get None for undefined values
        cp = ConfigParser.SafeConfigParser(defaults, allow_no_value=True)
        # later config files overwrite earlier files
        cp.read([os.path.join(app_dir, 'nvpy.cfg'), os.path.join(home, 'nvpy.cfg'), os.path.join(home, '.nvpy.cfg')])
        
        self.sn_username = cp.get('default', 'sn_username')
        self.sn_password = cp.get('default', 'sn_password')
        # make logic to find in $HOME if not set
        self.db_path = cp.get('default', 'db_path')
        #  0 = alpha sort, 1 = last modified first
        self.sort_mode = cp.getint('default', 'sort_mode')
        self.housekeeping_interval = cp.getint('default', 'housekeeping_interval')
        self.housekeeping_interval_ms = self.housekeeping_interval * 1000
        
        self.font_family = cp.get('default', 'font_family')
        self.font_size = cp.getint('default', 'font_size')
        
class NotesListModel(SubjectMixin):
    """
    @ivar list: List of (str key, dict note) objects.
    """
    def __init__(self):
        # call mixin ctor
        SubjectMixin.__init__(self)
        
        self.list = []
        
    def set_list(self, alist):
        self.list = alist
        self.notify_observers('set:list', None)
        
    def get_idx(self, key):
        """Find idx for passed LOCAL key. 
        """
        found = [i for i,e in enumerate(self.list) if e.key == key]
        if found:
            return found[0]
        
        else:
            return -1
    
class Controller:
    """Main application class.
    """
    
    def __init__(self):
        # setup appdir
        if hasattr(sys, 'frozen') and sys.frozen:
            self.appdir, _ = os.path.split(sys.executable)
            
        else:
            dirname = os.path.dirname(__file__)
            if dirname and dirname != os.curdir:
                self.appdir = dirname
            else:
                self.appdir = os.getcwd()

        # make sure it's the full path
        self.appdir = os.path.abspath(self.appdir)
        
        # should probably also look in $HOME
        self.config = Config(self.appdir)
        self.config.app_version = self.get_version()
        
        # read our database of notes into memory
        # and sync with simplenote.
        c = self.config
        notes_db_config = KeyValueObject(db_path=c.db_path, sn_username=c.sn_username, sn_password=c.sn_password, sort_mode=c.sort_mode)
        self.notes_db = NotesDB(notes_db_config)
        self.notes_db.add_observer('synced:note', self.observer_notes_db_synced_note)
        self.notes_db.add_observer('change:note-status', self.observer_notes_db_change_note_status)
        self.notes_db.add_observer('progress:sync_full', self.observer_notes_db_sync_full)

        self.notes_list_model = NotesListModel()
        
        # create the interface
        self.view = view.View(self.config, self.notes_list_model)
        # we want to be notified when the user does stuff
        self.view.add_observer('click:notelink',
                self.observer_view_click_notelink)
        self.view.add_observer('delete:note', self.observer_view_delete_note)
        self.view.add_observer('select:note', self.observer_view_select_note)
        self.view.add_observer('change:entry', self.observer_view_change_entry)
        self.view.add_observer('change:text', self.observer_view_change_text)
        self.view.add_observer('create:note', self.observer_view_create_note)
        self.view.add_observer('keep:house', self.observer_view_keep_house)
        self.view.add_observer('command:markdown',
                self.observer_view_markdown)
        self.view.add_observer('command:rest',
                self.observer_view_rest)
        self.view.add_observer('command:sync_full', lambda v, et, e: self.sync_full())
        self.view.add_observer('command:sync_current_note',
                self.observer_view_sync_current_note)
        
        self.view.add_observer('close', self.observer_view_close)
        
        # nn is a list of (key, note) objects
        nn = self.notes_db.filter_notes()
        # this will trigger the list_change event
        self.notes_list_model.set_list(nn)

        # we'll use this to keep track of the currently selected note
        # we only use idx, because key could change from right under us.
        self.selected_note_idx = -1
        self.view.select_note(0)
        
        # perform full sync with server, and refresh notes list if successful
        self.sync_full()
                
    def get_selected_note_key(self):
        if self.selected_note_idx >= 0:
            return self.notes_list_model.list[self.selected_note_idx].key
        else:
            return None
                
    def get_version(self):
        return "0.6"
    
    def main_loop(self):
        self.view.main_loop()
        
    def observer_notes_db_change_note_status(self, notes_db, evt_type, evt):
        skey = self.get_selected_note_key()
        if skey == evt.key:
            self.view.set_note_status(self.notes_db.get_note_status(skey))
            
    def observer_notes_db_sync_full(self, notes_db, evt_type, evt):
        print evt.msg
        self.view.set_status_text(evt.msg)
        
    def observer_notes_db_synced_note(self, notes_db, evt_type, evt):
        """This observer gets called only when a note returns from
        a sync that's more recent than our most recent mod to that note.
        """
        
        selected_note_o = self.notes_list_model.list[self.selected_note_idx]
        # if the note synced back matches our currently selected note,
        # we overwrite.
        
        if selected_note_o.key == evt.lkey:
            if selected_note_o.note['content'] != evt.old_note['content']:
                self.view.mute('change:text')
                # in this case, we want to keep the user's undo buffer so that they
                # can undo synced back changes if they would want to.
                self.view.set_text(selected_note_o.note['content'], reset_undo=False)
                self.view.unmute('change:text')

    def observer_view_click_notelink(self, view, evt_type, note_name):
        # find note_name in titles, try to jump to that note
        # if not in current list, change search string in case 
        # it's somewhere else
        # FIXME: implement find_note_by_name
        idx = self.view.select_note_by_name(note_name)
        
        if idx < 0:
            # this means a note with that name was not found
            # because nvpy kicks ass, it then assumes the contents of [[]]
            # to be a new regular expression to search for in the notes db.
            self.view.set_search_entry_text(note_name)
        
    def observer_view_delete_note(self, view, evt_type, evt):
        # delete note from notes_db
        # remove the note from the notes_list_model.list
        
        # if these two are not equal, something is not kosher.
        assert(evt.sel == self.selected_note_idx)

        # delete the note        
        key = self.get_selected_note_key()
        self.notes_db.delete_note(key)
        
        # easiest now is just to regenerate the list by resetting search string
        self.view.set_search_entry_text(self.view.get_search_entry_text())

    def helper_markdown_to_html(self):
        if self.selected_note_idx >= 0:
            key = self.notes_list_model.list[self.selected_note_idx].key
            c = self.notes_db.get_note_content(key)
            if HAVE_MARKDOWN:
                html = markdown.markdown(c)
                
            else:
                html = "<p>python markdown not installed, required for rendering to HTML.</p>"
                html += "<p>Please install with \"pip install markdown\".</p>"
                
            # create filename based on key
            fn = os.path.join(self.config.db_path, key + '.html')
            f = codecs.open(fn, mode='wb', encoding='utf-8')
            s = u"""
<html>
<head>
<meta http-equiv="refresh" content="5">
</head>
<body>
%s
</body>
</html>
            """ % (html,)
            f.write(s)
            f.close()
            return fn
        
    def helper_rest_to_html(self):
        if self.selected_note_idx >= 0:
            key = self.notes_list_model.list[self.selected_note_idx].key
            c = self.notes_db.get_note_content(key)
            if HAVE_DOCUTILS:
                # this gives the whole document
                html = docutils.core.publish_string(c, writer_name='html')
                # publish_parts("*anurag*",writer_name='html')['body']
                # gives just the desired part of the tree
                
            else:
                html = "<p>python docutils not installed, required for rendering reST to HTML.</p>"
                html += "<p>Please install with \"pip install docutils\".</p>"
                
            # create filename based on key
            fn = os.path.join(self.config.db_path, key + '_rest.html')
            f = codecs.open(fn, mode='wb', encoding='utf-8')
            # we keep this for later, in case we want to modify rest output
            # or combine it with our own headers.
            s = u"""
%s
            """ % (html,)
            f.write(s)
            f.close()
            return fn

    def observer_view_markdown(self, view, evt_type, evt):
        fn = self.helper_markdown_to_html()
        # turn filename into URI (mac wants this)
        fn_uri = 'file://' + os.path.abspath(fn)
        webbrowser.open(fn_uri)
        
    def observer_view_rest(self, view, evt_type, evt):
        fn = self.helper_rest_to_html()
        # turn filename into URI (mac wants this)
        fn_uri = 'file://' + os.path.abspath(fn)
        webbrowser.open(fn_uri)
        
    def observer_view_keep_house(self, view, evt_type, evt):
        # queue up all notes that need to be saved
        nsaved = self.notes_db.save_threaded()
        nsynced, sync_errors = self.notes_db.sync_to_server_threaded()
        
        # get list of note titles, and pass to view to check and fix if necessary
        qlen = self.notes_db.get_ss_queue_len() 
        if qlen > 0:
            self.view.set_status_text('Saving and syncing, %d notes in the queue.' % (qlen,))
        else:
            self.view.set_status_text('Idle.')

        # in continous rendering mode, we also generate a new HTML
        # the browser, if open, will refresh!
        if self.view.get_continuous_rendering():
            self.helper_markdown_to_html()
        
    def observer_view_select_note(self, view, evt_type, evt):
        self.select_note(evt.sel)

    def observer_view_sync_current_note(self, view, evt_type, evt):
        if self.selected_note_idx >= 0:
            key = self.notes_list_model.list[self.selected_note_idx].key
            # this call will update our in-memory version if necessary
            ret = self.notes_db.sync_note_unthreaded(key)
            if ret and ret[1] == True:
                self.view.update_selected_note_text(
                        self.notes_db.notes[key]['content'])
                self.view.set_status_text(
                'Synced updated note from server.')

            elif ret[1] == False:
                self.view.set_status_text(
                        'Server had nothing newer for this note.')

            elif ret is None:
                self.view.set_status_text(
                        'Unable to sync with server. Offline?')

            
    def observer_view_change_entry(self, view, evt_type, evt):
        # store the currently selected note key
        k = self.get_selected_note_key()
        # for each new evt.value coming in, get a new list from the notes_db
        # and set it in the notes_list_model
        nn = self.notes_db.filter_notes(evt.value)
        self.notes_list_model.set_list(nn)

        idx = self.notes_list_model.get_idx(k)

        if idx < 0:
            self.view.select_note(0)
            
        else:
            self.view.select_note(idx, silent=True)
            # we have a new search string, but did not make any text changes
            # so we have to update the search highlighting here.
            self.view.activate_search_string_highlights()

    def observer_view_change_text(self, view, evt_type, evt):
        # get new text and update our database
        # need local key of currently selected note for this
        if self.selected_note_idx >= 0:
            key = self.notes_list_model.list[self.selected_note_idx].key
            self.notes_db.set_note_content(key,
                                           self.view.get_text())
            
    def observer_view_close(self, view, evt_type, evt):
        # do a last full sync before we go!
        #self.sync_full()
        pass
        
    def observer_view_create_note(self, view, evt_type, evt):
        # create the note
        new_key = self.notes_db.create_note(evt.title)
        # clear the search entry, this should trigger a new list being returned
        self.view.set_search_entry_text('')
        # we should focus on our thingy
        idx = self.notes_list_model.get_idx(new_key)
        self.view.select_note(idx)
    
    def select_note(self, idx):
        if idx >= 0:
            key = self.notes_list_model.list[idx].key
            c = self.notes_db.get_note_content(key)

        else:
            key = None
            c = ''
            idx = -1
        
        self.selected_note_idx = idx

        # when we do this, we don't want the change:text event thanks
        self.view.mute('change:text')
        self.view.set_text(c)
        if key:
            self.view.set_note_status(self.notes_db.get_note_status(key))
        self.view.unmute('change:text')

    def sync_full(self):
        try:
            self.notes_db.sync_full()
        except SyncError:
            pass
        
        else:
            # regenerate display list
            # reselect old selection
            # put cursor where it used to be.
            self.view.refresh_notes_list()
        

def main():
    controller = Controller()
    controller.main_loop()
    

if __name__ == '__main__':
    main()

