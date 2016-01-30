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
import logging
from logging.handlers import RotatingFileHandler
from notes_db import NotesDB, SyncError, ReadError, WriteError
import argparse
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

VERSION = "1.0.0 BETA2"


class Config:
    """
    @ivar files_read: list of config files that were parsed.
    @ivar ok: True if config files had a default section, False otherwise.
    """
    def __init__(self, app_dir):
        """
        @param app_dir: the directory containing nvpy.py
        """

        self.app_dir = app_dir
        # cross-platform way of getting home dir!
        # http://stackoverflow.com/a/4028943/532513
        home = os.path.abspath(os.path.expanduser('~'))
        defaults = {'app_dir': app_dir,
                    'appdir': app_dir,
                    'home': home,
                    'notes_as_txt': '0',
                    'housekeeping_interval': '2',
                    'search_mode': 'gstyle',
                    'case_sensitive': '1',
                    'search_tags': '1',
                    'sort_mode': '1',
                    'pinned_ontop': '1',
                    'db_path': os.path.join(home, '.nvpy'),
                    'txt_path': os.path.join(home, '.nvpy/notes'),
                    'theme': 'default',
                    'font_family': 'Courier',  # monospaced on all platforms
                    'font_size': '10',
                    'list_font_family': 'Helvetica',  # sans on all platforms
                    'list_font_family_fixed': 'Courier',  # monospace on all platforms
                    'list_font_size': '10',
                    'layout': 'horizontal',
                    'print_columns': '0',
                    'background_color': 'white',
                    'sn_username': '',
                    'sn_password': '',
                    'simplenote_sync': '1',
                    'debug': '1',
                    # Filename or filepath to a css file used style the rendered
                    # output; e.g. nvpy.css or /path/to/my.css
                    'rest_css_path': None,
                   }

        # parse command-line arguments
        args = self.parse_cmd_line_opts()

        # later config files overwrite earlier files
        # try a number of alternatives
        cfg_files = [os.path.join(app_dir, 'nvpy.cfg'),
                     os.path.join(home, 'nvpy.cfg'),
                     os.path.join(home, '.nvpy.cfg'),
                     os.path.join(home, '.nvpy'),
                     os.path.join(home, '.nvpyrc')]

        # user has specified either a specific path to a CFG file, or a
        # path relative to the nvpy.py location. specific takes precedence.
        if args is not None and args.cfg is not None:
            cfg_files.extend([os.path.join(app_dir, args.cfg), args.cfg])

        cp = ConfigParser.SafeConfigParser(defaults)
        self.files_read = cp.read(cfg_files)

        cfg_sec = 'nvpy'

        if not cp.has_section(cfg_sec):
            cp.add_section(cfg_sec)
            self.ok = False

        else:
            self.ok = True

        # for the username and password, we don't want interpolation,
        # hence the raw parameter. Fixes
        # https://github.com/cpbotha/nvpy/issues/9
        self.sn_username = cp.get(cfg_sec, 'sn_username', raw=True)
        self.sn_password = cp.get(cfg_sec, 'sn_password', raw=True)
        self.simplenote_sync = cp.getint(cfg_sec, 'simplenote_sync')
        # make logic to find in $HOME if not set
        self.db_path = cp.get(cfg_sec, 'db_path')
        #  0 = alpha sort, 1 = last modified first
        self.notes_as_txt = cp.getint(cfg_sec, 'notes_as_txt')
        self.txt_path = os.path.join(home, cp.get(cfg_sec, 'txt_path'))
        self.search_mode = cp.get(cfg_sec, 'search_mode')
        self.case_sensitive = cp.getint(cfg_sec, 'case_sensitive')
        self.search_tags = cp.getint(cfg_sec, 'search_tags')
        self.sort_mode = cp.getint(cfg_sec, 'sort_mode')
        self.pinned_ontop = cp.getint(cfg_sec, 'pinned_ontop')
        self.housekeeping_interval = cp.getint(cfg_sec, 'housekeeping_interval')
        self.housekeeping_interval_ms = self.housekeeping_interval * 1000

        self.theme = cp.get(cfg_sec, 'theme')
        self.font_family = cp.get(cfg_sec, 'font_family')
        self.font_size = cp.getint(cfg_sec, 'font_size')

        self.list_font_family = cp.get(cfg_sec, 'list_font_family')
        self.list_font_family_fixed = cp.get(cfg_sec, 'list_font_family_fixed')
        self.list_font_size = cp.getint(cfg_sec, 'list_font_size')

        self.layout = cp.get(cfg_sec, 'layout')
        self.print_columns = cp.getint(cfg_sec, 'print_columns')

        self.background_color = cp.get(cfg_sec, 'background_color')

        self.rest_css_path = cp.get(cfg_sec, 'rest_css_path')
        self.debug = cp.getint(cfg_sec, 'debug')

    def parse_cmd_line_opts(self):
        if __name__ != '__main__':
            return None

        parser = argparse.ArgumentParser()
        parser.add_argument('--cfg', '-c', default='', dest='cfg',
                            metavar='nvpy.cfg', help='path to config file')
        args = parser.parse_args()
        return args


class NotesListModel(SubjectMixin):
    """
    @ivar list: List of (str key, dict note) objects.
    """
    def __init__(self):
        # call mixin ctor
        SubjectMixin.__init__(self)

        self.list = []
        self.match_regexps = []

    def set_list(self, alist):
        self.list = alist
        self.notify_observers('set:list', None)

    def get_idx(self, key):
        """Find idx for passed LOCAL key.
        """
        found = [i for i, e in enumerate(self.list) if e.key == key]
        if found:
            return found[0]

        else:
            return -1


class Controller:
    """Main application class.
    """

    def __init__(self, config):
        # should probably also look in $HOME
        self.config = config
        self.config.app_version = VERSION

        # configure logging module
        #############################

        # first create db directory if it doesn't exist yet.
        if not os.path.exists(self.config.db_path):
            os.mkdir(self.config.db_path)

        log_filename = os.path.join(self.config.db_path, 'nvpy.log')
        # file will get nuked when it reaches 100kB
        lhandler = RotatingFileHandler(log_filename, maxBytes=100000, backupCount=1)
        lhandler.setLevel(logging.DEBUG)
        lhandler.setFormatter(logging.Formatter(fmt='%(asctime)s - %(levelname)s - %(message)s'))
        # we get the root logger and configure it
        logger = logging.getLogger()
        if self.config.debug == 1:
            logger.setLevel(logging.DEBUG)
        logger.addHandler(lhandler)
        # this will go to the root logger
        logging.debug('nvpy logging initialized')

        logging.debug('config read from %s' % (str(self.config.files_read),))

        if self.config.sn_username == '':
            self.config.simplenote_sync = 0

        css = self.config.rest_css_path
        if css:
            if css.startswith("~/"):
                # On Mac, paths that start with '~/' aren't found by path.exists
                css = css.replace(
                    "~", os.path.abspath(os.path.expanduser('~')), 1)
                self.config.rest_css_path = css
            if not os.path.exists(css):
                # Couldn't find the user-defined css file. Use docutils css instead.
                self.config.rest_css_path = None

        self.notes_list_model = NotesListModel()
        # create the interface
        self.view = view.View(self.config, self.notes_list_model)

        # read our database of notes into memory
        # and sync with simplenote.
        try:
            self.notes_db = NotesDB(self.config)

        except ReadError, e:
            emsg = "Please check nvpy.log.\n" + str(e)
            self.view.show_error('Sync error', emsg)
            exit(1)

        self.notes_db.add_observer('synced:note', self.observer_notes_db_synced_note)
        self.notes_db.add_observer('change:note-status', self.observer_notes_db_change_note_status)

        if self.config.simplenote_sync:
            self.notes_db.add_observer('progress:sync_full', self.observer_notes_db_sync_full)
            self.sync_full()

        # we want to be notified when the user does stuff
        self.view.add_observer('click:notelink',
                self.observer_view_click_notelink)
        self.view.add_observer('delete:note', self.observer_view_delete_note)
        self.view.add_observer('select:note', self.observer_view_select_note)
        self.view.add_observer('change:entry', self.observer_view_change_entry)
        self.view.add_observer('change:text', self.observer_view_change_text)
        self.view.add_observer('change:pinned', self.observer_view_change_pinned)
        self.view.add_observer('create:note', self.observer_view_create_note)
        self.view.add_observer('keep:house', self.observer_view_keep_house)
        self.view.add_observer('command:markdown', self.observer_view_markdown)
        self.view.add_observer('command:rest', self.observer_view_rest)
        self.view.add_observer('delete:tag', self.observer_view_delete_tag)
        self.view.add_observer('add:tag', self.observer_view_add_tag)

        if self.config.simplenote_sync:
            self.view.add_observer('command:sync_full', lambda v, et, e: self.sync_full())
            self.view.add_observer('command:sync_current_note', self.observer_view_sync_current_note)

        self.view.add_observer('close', self.observer_view_close)

        # setup UI to reflect our search mode and case sensitivity
        self.view.set_cs(self.config.case_sensitive, silent=True)
        self.view.set_search_mode(self.config.search_mode, silent=True)

        self.view.add_observer('change:cs', self.observer_view_change_cs)
        self.view.add_observer('change:search_mode', self.observer_view_change_search_mode)

        # nn is a list of (key, note) objects
        nn, match_regexp, active_notes = self.notes_db.filter_notes()
        # this will trigger the list_change event
        self.notes_list_model.set_list(nn)
        self.notes_list_model.match_regexp = match_regexp
        self.view.set_note_tally(len(nn), active_notes, len(self.notes_db.notes))

        # we'll use this to keep track of the currently selected note
        # we only use idx, because key could change from right under us.
        self.selected_note_idx = -1
        self.view.select_note(0)

    def get_selected_note_key(self):
        if self.selected_note_idx >= 0:
            return self.notes_list_model.list[self.selected_note_idx].key
        else:
            return None

    def main_loop(self):
        if not self.config.files_read:
            self.view.show_warning('No config file',
                                  'Could not read any configuration files. See https://github.com/cpbotha/nvpy for details.')

        elif not self.config.ok:
            wmsg = ('Please rename [default] to [nvpy] in %s. ' + \
                    'Config file format changed after nvPY 0.8.') % \
            (str(self.config.files_read),)
            self.view.show_warning('Rename config section', wmsg)

        self.view.main_loop()

    def observer_notes_db_change_note_status(self, notes_db, evt_type, evt):
        skey = self.get_selected_note_key()
        if skey == evt.key:
            self.view.set_note_status(self.notes_db.get_note_status(skey))

    def observer_notes_db_sync_full(self, notes_db, evt_type, evt):
        logging.debug(evt.msg)
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
                self.view.mute_note_data_changes()
                # in this case, we want to keep the user's undo buffer so that they
                # can undo synced back changes if they would want to.
                self.view.set_note_data(selected_note_o.note, reset_undo=False)
                self.view.unmute_note_data_changes()

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

        # first get key of note that is to be deleted
        key = self.get_selected_note_key()

        # then try to select after the one that is to be deleted
        nidx = evt.sel + 1
        if nidx >= 0 and nidx < self.view.get_number_of_notes():
            self.view.select_note(nidx)

        # finally delete the note
        self.notes_db.delete_note(key)

        # easiest now is just to regenerate the list by resetting search string
        # if the note after the deleted one is already selected, this will
        # simply keep that selection!
        self.view.set_search_entry_text(self.view.get_search_entry_text())

    def helper_markdown_to_html(self):
        if self.selected_note_idx >= 0:
            key = self.notes_list_model.list[self.selected_note_idx].key
            c = self.notes_db.get_note_content(key)
            logging.debug("Trying to convert %s to html." % (key,))
            if HAVE_MARKDOWN:
                logging.debug("Convert note %s to html." % (key,))
                html = markdown.markdown(c)
                logging.debug("Convert done.")

            else:
                logging.debug("Markdown not installed.")
                html = "<p>python markdown not installed, required for rendering to HTML.</p>"
                html += "<p>Please install with \"pip install markdown\".</p>"

            # create filename based on key
            fn = os.path.join(self.config.db_path, key + '.html')
            f = codecs.open(fn, mode='wb', encoding='utf-8')
            s = u"""
<html>
<head>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8"/>
%s
</head>
<body>
%s
</body>
</html>
            """ % ('<meta http-equiv="refresh" content="5">' if self.view.get_continuous_rendering() else "",html,)
            f.write(s)
            f.close()
            return fn

    def helper_rest_to_html(self):
        if self.selected_note_idx >= 0:
            key = self.notes_list_model.list[self.selected_note_idx].key
            c = self.notes_db.get_note_content(key)
            if HAVE_DOCUTILS:
                settings = {}
                if self.config.rest_css_path:
                    settings['stylesheet_path'] = self.config.rest_css_path
                # this gives the whole document
                html = docutils.core.publish_string(
                    c, writer_name='html', settings_overrides=settings)
                # publish_parts("*anurag*",writer_name='html')['body']
                # gives just the desired part of the tree

            else:
                html = "<p>python docutils not installed, required for rendering reST to HTML.</p>"
                html += "<p>Please install with \"pip install docutils\".</p>"

            # create filename based on key
            fn = os.path.join(self.config.db_path, key + '_rest.html')
            f = codecs.open(fn, mode='wb', encoding='utf-8')

            # explicit decode from utf8 into unicode object. If we don't
            # specify utf8, python falls back to default ascii and then we get
            # "'ascii' codec can't decode byte" error
            s = u"""
%s
            """ % (unicode(html, 'utf8'),)

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

    def helper_save_sync_msg(self):

        # Saving 2 notes. Syncing 3 notes, waiting for simplenote server.
        # All notes saved. All notes synced.

        saven = self.notes_db.get_save_queue_len()

        if self.config.simplenote_sync:
            syncn = self.notes_db.get_sync_queue_len()
            wfsn = self.notes_db.waiting_for_simplenote
        else:
            syncn = wfsn = 0

        savet = 'Saving %d notes.' % (saven,) if saven > 0 else ''
        synct = 'Waiting to sync %d notes.' % (syncn,) if syncn > 0 else ''
        wfsnt = 'Syncing with simplenote server.' if wfsn else ''

        return ' '.join([i for i in [savet, synct, wfsnt] if i])

    def observer_view_keep_house(self, view, evt_type, evt):
        # queue up all notes that need to be saved
        nsaved = self.notes_db.save_threaded()
        msg = self.helper_save_sync_msg()

        if self.config.simplenote_sync:
            nsynced, sync_errors = self.notes_db.sync_to_server_threaded()
            if sync_errors:
                msg = ' '.join([i for i in [msg, 'Could not connect to simplenote server.'] if i])

        self.view.set_status_text(msg)

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
                self.view.update_selected_note_data(
                        self.notes_db.notes[key])
                self.view.set_status_text(
                'Synced updated note from server.')

            elif ret[1] == False:
                self.view.set_status_text(
                        'Server had nothing newer for this note.')

            elif ret is None:
                self.view.set_status_text(
                        'Unable to sync with server. Offline?')

    def observer_view_change_cs(self, view, evt_type, evt):
        # evt.value is the new value
        # only do something if user has really toggled
        if evt.value != self.config.case_sensitive:
            self.config.case_sensitive = evt.value
            self.view.refresh_notes_list()

    def observer_view_change_search_mode(self, view, evt_type, evt):
        if evt.value != self.config.search_mode:
            self.config.search_mode = evt.value
            self.view.refresh_notes_list()

    def observer_view_change_entry(self, view, evt_type, evt):
        # store the currently selected note key
        k = self.get_selected_note_key()
        # for each new evt.value coming in, get a new list from the notes_db
        # and set it in the notes_list_model
        nn, match_regexp, active_notes = self.notes_db.filter_notes(evt.value)
        self.notes_list_model.set_list(nn)
        self.notes_list_model.match_regexp = match_regexp
        self.view.set_note_tally(len(nn), active_notes, len(self.notes_db.notes))

        idx = self.notes_list_model.get_idx(k)

        if idx < 0:
            self.view.select_note(0)
            # the user is typing, but her previously selected note is
            # not in the new filtered list. as a convenience, we move
            # the text in the text widget so it's on the first
            # occurrence of the search string, IF there's such an
            # occurrence.
            self.view.see_first_search_instance()

        else:
            # we don't want new text to be implanted (YET) so we keep this silent
            # if it does turn out to be new note content, this will be handled
            # a few lines down.
            self.view.select_note(idx, silent=True)
            # but of course we DO have to record the possibly new IDX!!
            self.selected_note_idx = idx

            # see if the note has been updated (content, tags, pin)
            new_note = self.notes_db.get_note(k)

            # check if the currently selected note is different from the one
            # currently being displayed. this could happen if a sync gets
            # a new note of the server to replace the currently displayed one.
            if self.view.is_note_different(new_note):
                logging.debug("Currently selected note %s replaced by newer from server." % (k,))
                # carefully update currently selected note
                # restore cursor position, search and link highlights
                self.view.update_selected_note_data(new_note)

            else:
                # we have a new search string, but did not make any text changes
                # so we have to update the search highlighting here. (usually
                # text changes trigger this)
                self.view.activate_search_string_highlights()

    def observer_view_change_text(self, view, evt_type, evt):
        # get new text and update our database
        # need local key of currently selected note for this
        if self.selected_note_idx >= 0:
            key = self.notes_list_model.list[self.selected_note_idx].key
            self.notes_db.set_note_content(key,
                                           self.view.get_text())

    def observer_view_change_tags(self, view, evt_type, evt):
        # get new text and update our database
        # need local key of currently selected note for this
        if self.selected_note_idx >= 0:
            key = self.notes_list_model.list[self.selected_note_idx].key
            self.notes_db.set_note_tags(key, evt.value)
            self.view.cmd_notes_list_select()

    def observer_view_delete_tag(self, view, evt_type, evt):
        key = self.notes_list_model.list[self.selected_note_idx].key
        self.notes_db.delete_note_tag(key, evt.tag)
        self.view.cmd_notes_list_select()
    
    def observer_view_add_tag(self, view, evt_type, evt):
        key = self.notes_list_model.list[self.selected_note_idx].key
        self.notes_db.add_note_tags(key, evt.tags)
        self.view.cmd_notes_list_select()
        self.view.tags_entry_var.set('')

    def observer_view_change_pinned(self, view, evt_type, evt):
        # get new text and update our database
        # need local key of currently selected note for this
        if self.selected_note_idx >= 0:
            key = self.notes_list_model.list[self.selected_note_idx].key
            self.notes_db.set_note_pinned(key, evt.value)

    def observer_view_close(self, view, evt_type, evt):
        # check that everything has been saved and synced before exiting

        # first make sure all our queues are up to date
        self.notes_db.save_threaded()
        if self.config.simplenote_sync:
            self.notes_db.sync_to_server_threaded(wait_for_idle=False)
            syncn = self.notes_db.get_sync_queue_len()
            wfsn = self.notes_db.waiting_for_simplenote
        else:
            syncn = wfsn = 0

        # then check all queues
        saven = self.notes_db.get_save_queue_len()

        # if there's still something to do, warn the user.
        if saven or syncn or wfsn:
            msg = "Are you sure you want to exit? I'm still busy: " + self.helper_save_sync_msg()
            really_want_to_exit = self.view.askyesno("Confirm exit", msg)

            if really_want_to_exit:
                self.view.close()

        else:
            self.view.close()

    def observer_view_create_note(self, view, evt_type, evt):
        # create the note
        new_key = self.notes_db.create_note(evt.title)
        # clear the search entry, this should trigger a new list being returned
        self.view.set_search_entry_text('')
        # we should focus on our thingy
        idx = self.notes_list_model.get_idx(new_key)
        self.view.select_note(idx)

    def select_note(self, idx):
        """Called whenever user selects a different note via the UI.

        This sets all machinery in motion to put the now note's data in all
        the right places.

        @param idx:
        @return:
        """
        if idx >= 0:
            key = self.notes_list_model.list[idx].key
            note = self.notes_db.get_note(key)
            # valid note, so note editing should be enabled
            self.view.set_note_editing(True)

        else:
            key = None
            note = None
            idx = -1
            # no note selected, so we clear the UI (and display a clear
            # message that no note is selected) and we disable note
            # editing controls.
            self.view.clear_note_ui()
            self.view.set_note_editing(False)

        self.selected_note_idx = idx

        # when we do this, we don't want the change:{text,tags,pinned} events
        # because those should only fire when they are changed through the UI
        self.view.mute_note_data_changes()
        self.view.set_note_data(note)
        if key:
            self.view.set_note_status(self.notes_db.get_note_status(key))

        self.view.unmute_note_data_changes()

    def sync_full(self):
        try:
            sync_from_server_errors = self.notes_db.sync_full()

        except SyncError, e:
            self.view.show_error('Sync error', e)
        except WriteError, e:
            emsg = "Please check nvpy.log.\n" + str(e)
            self.view.show_error('Sync error', emsg)
            exit(1)

        else:
            # regenerate display list
            # reselect old selection
            # put cursor where it used to be.
            self.view.refresh_notes_list()

            if sync_from_server_errors > 0:
                self.view.show_error('Error syncing notes from server', 'Error syncing %d notes from server. Please check nvpy.log for details.' % (sync_from_server_errors,))


def main():
    # setup appdir
    if hasattr(sys, 'frozen') and sys.frozen:
        appdir, _ = os.path.split(sys.executable)

    else:
        dirname, _ = os.path.split(os.path.realpath(__file__))
        if dirname and dirname != os.curdir:
            appdir = dirname
        else:
            appdir = os.getcwd()

    # make sure it's the full path
    appdir_full_path = os.path.abspath(appdir)

    config = Config(appdir_full_path)

    controller = Controller(config)
    controller.main_loop()


if __name__ == '__main__':
    main()
