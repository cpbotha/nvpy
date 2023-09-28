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
""" Controller and Config classes """
import contextlib
import enum
import sys
import codecs
import time
from configparser import ConfigParser
import logging
from logging.handlers import RotatingFileHandler
import argparse
import os
import traceback
import threading
import re
import typing
import webbrowser
from http.client import HTTPException
import pathlib
import platform

from .notes_db import NotesDB, SyncError, ReadError, WriteError, MergedSorter, PinnedSorter, AlphaSorter, DateSorter, \
    AlphaNumSorter, Sorter, NoteInfo
from . import tk
from .utils import SubjectMixin
from . import view
from .version import VERSION
from . import events

try:
    import markdown  # type:ignore
except ImportError:
    HAVE_MARKDOWN = False
else:
    HAVE_MARKDOWN = True
    DEFAULT_MARKDOWN_EXTS = (
        # Add 'fenced code block' syntax support.
        # If you try to convert without this extension, code block is treated as inline code.
        # https://python-markdown.github.io/extensions/fenced_code_blocks/
        'markdown.extensions.fenced_code',
        # Add table syntax support.
        # https://python-markdown.github.io/extensions/tables/
        'markdown.extensions.tables',
    )

try:
    import docutils
    import docutils.core
except ImportError:
    HAVE_DOCUTILS = False
else:
    HAVE_DOCUTILS = True

PathList = typing.List[pathlib.Path]


class ColorConfig(typing.NamedTuple):
    # Text color.
    text: str
    # Background color of selected note.
    selected_note: str
    # Text color for note info (title, tags, updated date, etc).
    note_info: str
    # Text color for highlighted note info.
    highlight_note_info: str
    # Text color for URL.
    url: str
    # Background color for URL selection.
    url_selection_background: str
    # Background color.
    background: str
    # Background color of highlighted area.
    highlight_background: str


@enum.unique
class SortMode(enum.Enum):
    """ Enum variables for note sorting order """

    # Sort in alphabetic order.
    ALPHA = 0
    # Sort by modification date.
    MODIFICATION_DATE = 1
    # Sort by creation date.
    CREATION_DATE = 2
    # Sort in alphanumeric order.
    ALPHA_NUM = 3

    @classmethod
    def human_friendly_names(cls) -> typing.Dict[str, 'SortMode']:
        return {
            'title (alphabetical order)': cls.ALPHA,
            'title (alphanumerical order)': cls.ALPHA_NUM,
            'modification date': cls.MODIFICATION_DATE,
            'creation date': cls.CREATION_DATE,
        }


class Config:
    """
    @ivar files_read: list of config files that were parsed.
    @ivar ok: True if config files had a default section, False otherwise.
    """

    def __init__(self, app_dir: str, cfg_files: typing.Optional[PathList] = None):
        """
        @param app_dir: the directory containing nvpy.py
        @param cfg_files: List of path to configuration files (optional)

        If cfg_files is omitted, Config reads configuration files from default locations.
        """
        is_linux = platform.system() == "Linux"

        self.app_dir = app_dir
        # cross-platform way of getting home dir!
        # http://stackoverflow.com/a/4028943/532513
        home = pathlib.Path.home()

        # the file that we write user settings to, which is different
        # from the configuration files
        self.settings_file = home / '.nvpy_settings'
        if is_linux:
            env_dir = os.environ.get("XDG_CACHE_HOME")
            cache_dir = pathlib.Path(env_dir) if env_dir and os.path.isabs(env_dir) else home / ".cache"
            old_file = self.settings_file
            self.settings_file = cache_dir / "nvpy_settings"
            # Try deleting the nvpy_settings file in old location.
            # Use try-except instead of the missing_ok=True because Python 3.6 and 3.7 are not supported it.
            try:
                pathlib.Path(old_file).unlink()
            except FileNotFoundError:
                pass

        defaults = {
            'app_dir': app_dir,
            'appdir': app_dir,
            'home': home,
            'notes_as_txt': '0',
            'read_txt_extensions': 'txt,mkdn,md,mdown,markdown',
            'housekeeping_interval': '2',
            'search_mode': 'gstyle',
            'case_sensitive': '1',
            'search_tags': '1',
            'sort_mode': '1',
            'pinned_ontop': '1',
            'db_path': os.path.join(home, '.nvpy'),
            'txt_path': os.path.join(home, '.nvpy/notes'),
            'replace_filename_spaces': '1',
            'theme': 'default',
            'font_family': 'Courier',  # monospaced on all platforms
            'font_size': '10',
            'list_font_family': 'Helvetica',  # sans on all platforms
            'list_font_family_fixed': 'Courier',  # monospace on all platforms
            'list_font_size': '10',
            'list_hide_time': '0',
            'list_hide_tags': '0',
            'underline_urls': 'true',
            'layout': 'horizontal',
            'print_columns': '0',
            'text_color': 'black',
            'selected_note_color': 'light blue',
            'note_info_color': 'dark gray',
            'highlight_note_info_color': 'lightyellow',
            'url_color': '#03f',
            'url_selection_background_color': 'yellow',
            'background_color': 'white',
            'highlight_background_color': 'yellow',
            'sn_username': '',
            'sn_password': '',
            'simplenote_sync': '1',
            'debug': '1',
            # Filename or filepath to a css file used style the rendered
            # output; e.g. nvpy.css or /path/to/my.css
            'rest_css_path': '',
            'md_css_path': '',
            'md_extensions': '',
            'keep_search_keyword': 'false',
            'confirm_delete': 'true',
            'escape_to_exit': 'false',
            'confirm_exit': 'false',
            'streamline_interface': 'false',
            'use_profiler': 'false',
        }

        normalized_cfg_files = self._list_cfg_files(cfg_files)
        self.files_read, cp = self._load_cfg(defaults, normalized_cfg_files)

        cfg_sec = 'nvpy'

        if not cp.has_section(cfg_sec):
            cp.add_section(cfg_sec)
            self.ok = False

        else:
            self.ok = True

        self.app_version = VERSION
        # for the username and password, we don't want interpolation,
        # hence the raw parameter. Fixes
        # https://github.com/cpbotha/nvpy/issues/9
        self.sn_username = cp.get(cfg_sec, 'sn_username', raw=True)
        self.sn_password = cp.get(cfg_sec, 'sn_password', raw=True)
        self.simplenote_sync = cp.getint(cfg_sec, 'simplenote_sync')
        # make logic to find in $HOME if not set
        self.db_path = cp.get(cfg_sec, 'db_path')
        self.notes_as_txt = cp.getint(cfg_sec, 'notes_as_txt')
        self.read_txt_extensions = cp.get(cfg_sec, 'read_txt_extensions')
        self.txt_path = os.path.join(home, cp.get(cfg_sec, 'txt_path'))
        self.replace_filename_spaces = cp.getint(cfg_sec, 'replace_filename_spaces')
        self.search_mode = cp.get(cfg_sec, 'search_mode')
        self.case_sensitive = cp.getint(cfg_sec, 'case_sensitive')
        self.search_tags = cp.getint(cfg_sec, 'search_tags')
        # See nvpy.SortMode.
        self.sort_mode = SortMode(cp.getint(cfg_sec, 'sort_mode'))
        self.pinned_ontop = cp.getint(cfg_sec, 'pinned_ontop')
        self.housekeeping_interval = cp.getint(cfg_sec, 'housekeeping_interval')
        self.housekeeping_interval_ms = self.housekeeping_interval * 1000

        self.theme = cp.get(cfg_sec, 'theme')
        self.font_family = cp.get(cfg_sec, 'font_family')
        self.font_size = cp.getint(cfg_sec, 'font_size')

        self.list_font_family = cp.get(cfg_sec, 'list_font_family')
        self.list_font_family_fixed = cp.get(cfg_sec, 'list_font_family_fixed')
        self.list_font_size = cp.getint(cfg_sec, 'list_font_size')

        self.list_hide_time = cp.getint(cfg_sec, 'list_hide_time')
        self.list_hide_tags = cp.getint(cfg_sec, 'list_hide_tags')

        self.underline_urls = cp.getboolean(cfg_sec, 'underline_urls')

        self.layout = cp.get(cfg_sec, 'layout')
        self.print_columns = cp.getint(cfg_sec, 'print_columns')

        self.colors = ColorConfig(
            text=cp.get(cfg_sec, 'text_color'),
            selected_note=cp.get(cfg_sec, 'selected_note_color'),
            note_info=cp.get(cfg_sec, 'note_info_color'),
            highlight_note_info=cp.get(cfg_sec, 'highlight_note_info_color'),
            url=cp.get(cfg_sec, 'url_color'),
            url_selection_background=cp.get(cfg_sec, 'url_selection_background_color'),
            background=cp.get(cfg_sec, 'background_color'),
            highlight_background=cp.get(cfg_sec, 'highlight_background_color'),
        )

        self.rest_css_path = self._normalize_path(cp.get(cfg_sec, 'rest_css_path'))
        self.md_css_path = self._normalize_path(cp.get(cfg_sec, 'md_css_path'))
        self.md_extensions = cp.get(cfg_sec, 'md_extensions')
        self.debug = cp.getint(cfg_sec, 'debug')
        self.keep_search_keyword = cp.getboolean(cfg_sec, 'keep_search_keyword')
        self.confirm_delete = cp.getboolean(cfg_sec, 'confirm_delete')
        self.escape_to_exit = cp.getboolean(cfg_sec, 'escape_to_exit')
        self.confirm_exit = cp.getboolean(cfg_sec, 'confirm_exit')

        self.streamline_interface = cp.getboolean(cfg_sec, 'streamline_interface')

        self.warnings = []
        if cp.has_option(cfg_sec, 'background_full_sync'):
            w = lambda: logging.warning('"background_full_sync" option is removed.')
            self.warnings.append(w)

        self.use_profiler = cp.getboolean(cfg_sec, 'use_profiler')

    def _list_cfg_files(self, cfg_files: typing.Optional[PathList]) -> PathList:
        """ List up nvPY configuration files. """
        if cfg_files is None:
            # No configuration path specified. Use default locations.
            # Later config files overwrite earlier files try a number of alternatives.
            home = pathlib.Path.home()
            env_dir = os.environ.get("XDG_CONFIG_HOME")
            xdg_config_home = pathlib.Path(env_dir) if env_dir and os.path.isabs(env_dir) else home / ".config"
            cfg_files = [
                pathlib.Path(self.app_dir) / 'nvpy.cfg',
                home / 'nvpy.cfg',
                home / '.nvpy.cfg',
                home / '.nvpy',
                home / '.nvpyrc',
                xdg_config_home / 'nvpy.cfg',
            ]

        return cfg_files

    def _load_cfg(self, defaults: dict, cfg_files: PathList) -> typing.Tuple[typing.List[str], ConfigParser]:
        """ Load configuration files.
        If cfg argument is specified, read only specified file. Otherwise, read configuration files from some locations.

        Args:
            defaults: Dict of default key values.
            cfg: Path to config file.

        Returns:
            Returns following elements.
            1st element: List of config file paths.  It may be empty (list of zero length, not None).
            2nd element: ConfigParser object.
        """
        cp = ConfigParser(defaults)
        return cp.read(cfg_files), cp

    @staticmethod
    def _normalize_path(path: str) -> str:
        """ Normalize path for configuration option.
        If path is '', this function always returns ''. Otherwise, it returns absolute path.
        """
        if path == '':
            return ''
        return str(pathlib.Path(path).expanduser().absolute())

    @property
    def sorter(self):
        mode = SortMode(self.sort_mode)

        sorters: typing.List[Sorter] = []
        if self.pinned_ontop:
            sorters.append(PinnedSorter())

        if mode == SortMode.ALPHA:
            sorters.append(AlphaSorter())
        elif mode in [SortMode.MODIFICATION_DATE, SortMode.CREATION_DATE]:
            sorters.append(DateSorter(mode=mode))
        elif mode == SortMode.ALPHA_NUM:
            sorters.append(AlphaNumSorter())
        else:
            raise ValueError(f'invalid sort_mode: {mode}')

        return MergedSorter(*sorters)

    def show_warnings(self):
        """ Show warnings when using obsoleted option. """
        for w in self.warnings:
            w()

    def write_setting(self, section, key, value):
        """
        Write the key/value pair to the settngs file in the
        section specified. The settings file is useful for recording
        changes the user makes so that they can be remembered next time
        the application starts.
        """
        cp = ConfigParser()
        cp.read(self.settings_file)
        if not cp.has_section(section):
            cp.add_section(section)

        cp.set(section, key, "%s" % value)
        with open(self.settings_file, 'w') as configfile:
            cp.write(configfile)

        logging.debug("Wrote [%s] %s = %s to %s" % (section, key, value, self.settings_file))

    def read_setting(self, section, key):
        """
        Read the key in the specified section from the settings file,
        or returns None if not found.
        """
        cp = ConfigParser()
        cp.read(self.settings_file)
        if cp.has_section(section):
            if cp.has_option(section, key):
                return cp.get(section, key)
        return None


class NotesListModel(SubjectMixin):
    """
    @ivar list: List of (str key, dict note) objects.
    """

    def __init__(self):
        # call mixin ctor
        SubjectMixin.__init__(self)

        self.list: typing.List[NoteInfo] = []
        self.match_regexp: typing.Optional[typing.Pattern] = None

    def set_list(self, alist: typing.List[NoteInfo]):
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

    def get(self, key):
        idx = self.get_idx(key)
        if idx < 0:
            raise KeyError('Note is not found: key={}'.format(key))

        return self.list[idx]


class Controller:
    """Main application class.
    """

    def __init__(self, config: Config):
        self.config = config

        # configure logging module
        #############################

        # first create db directory if it doesn't exist yet.
        if not os.path.exists(self.config.db_path):
            os.mkdir(self.config.db_path)

        log_filename = os.path.join(self.config.db_path, 'nvpy.log')
        # file will get nuked when it reaches 100kB
        lhandler = RotatingFileHandler(log_filename, maxBytes=100000, backupCount=1, encoding='utf8')
        lhandler.setLevel(logging.DEBUG)
        lhandler.setFormatter(logging.Formatter(fmt='%(asctime)s - %(levelname)s - %(message)s'))
        # we get the root logger and configure it
        logger = logging.getLogger()
        if self.config.debug == 1:
            logger.setLevel(logging.DEBUG)
        logger.addHandler(lhandler)
        # this will go to the root logger
        logging.debug('nvpy logging initialized')

        logging.debug('config read from %s' % (str(self.config.files_read), ))
        self.config.show_warnings()

        if self.config.sn_username == '':
            self.config.simplenote_sync = 0

        self.notes_list_model = NotesListModel()
        # create the interface
        self.view = view.View(self.config, self.notes_list_model)

        try:
            # read our database of notes into memory
            # and sync with simplenote.
            try:
                self.notes_db = NotesDB(self.config)
            except ReadError as e:
                emsg = "Please check nvpy.log.\n" + str(e)
                self.view.show_error('Sync error', emsg)
                exit(1)

            self.notes_db.add_observer('saved:note', self.observer_notes_db_saved_note)
            self.notes_db.add_observer('synced:note', self.observer_notes_db_synced_note)
            self.notes_db.add_observer('change:note-status', self.observer_notes_db_change_note_status)

            if self.config.simplenote_sync:
                self.notes_db.add_observer('progress:sync_full', self.observer_notes_db_sync_full)
                self.notes_db.add_observer('error:sync_full', self.observer_notes_db_error_sync_full)
                self.notes_db.add_observer('complete:sync_full', self.observer_notes_db_complete_sync_full)

            # we want to be notified when the user does stuff
            self.view.add_observer('click:notelink', self.observer_view_click_notelink)
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
            self.view.add_observer('change:sort_mode', self.observer_view_change_sort_mode)
            self.view.add_observer('change:pinned_on_top', self.observer_view_change_pinned_on_top)

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
            self.selected_note_key = None
            self.view.select_note(0)

            if self.config.simplenote_sync:
                self.view.after(0, self.sync_full)
        except BaseException:
            # Initialization failed.  Stop all timers.
            self.view.cancel_timers()
            raise

    def main_loop(self):
        # SubjectMixin.handle_notifies() requires that main_loop must run on the main thread.
        assert SubjectMixin.MAIN_THREAD == threading.current_thread()

        if not self.config.files_read:
            self.view.show_warning(
                'No config file',
                'Could not read any configuration files. See https://github.com/cpbotha/nvpy for details.')

        elif not self.config.ok:
            wmsg = ('Please rename [default] to [nvpy] in %s. ' + \
                    'Config file format changed after nvPY 0.8.') % \
            (str(self.config.files_read),)
            self.view.show_warning('Rename config section', wmsg)

        def poll_notifies():
            self.view.after(100, poll_notifies)
            self.notes_db.handle_notifies()

        self.view.after(0, poll_notifies)
        try:
            self.view.main_loop()
        finally:
            # Cancel all timers before stop this program.
            self.view.cancel_timers()

    def observer_notes_db_change_note_status(self, notes_db, evt_type, evt: events.NoteStatusChangedEvent):
        skey = self.selected_note_key
        if skey == evt.key:
            self.view.set_note_status(self.notes_db.get_note_status(skey))

    def observer_notes_db_sync_full(self, notes_db, evt_type, evt: events.SyncProgressEvent):
        logging.debug(evt.msg)
        self.view.set_status_text(evt.msg)

        # regenerate display list
        # reselect old selection
        # put cursor where it used to be.
        self.view.refresh_notes_list()

        # change status to "Full syncing"
        self.update_note_status()

    def observer_notes_db_error_sync_full(self, notes_db, evt_type, evt: events.SyncFailedEvent):
        try:
            raise evt.error
        except (SyncError, HTTPException) as e:
            self.view.show_error('Sync error', e)
        except WriteError as e:
            emsg = "Please check nvpy.log.\n" + str(e)
            self.view.show_error('Sync error', emsg)
            exit(1)
        except Exception as e:
            crash_log = ''.join(traceback.format_exception(*evt.exc_info))
            logging.error(crash_log)
            emsg = 'An unexpected error has occurred.\n'\
                   'Please check nvpy.log.\n' \
                   + repr(e)
            self.view.show_error('Sync error', emsg)
            exit(1)

        # return normal status from "Full syning".
        self.update_note_status()

    def observer_notes_db_complete_sync_full(self, notes_db, evt_type, evt: events.SyncCompletedEvent):
        sync_from_server_errors = evt.errors
        if sync_from_server_errors > 0:
            self.view.show_error(
                'Error syncing notes from server',
                'Error syncing %d notes from server. Please check nvpy.log for details.' % (sync_from_server_errors, ))

        # return normal status from "Full syning".
        self.update_note_status()

    def observer_notes_db_saved_note(self, notes_db, evt_type, evt: events.NoteSavedEvent):
        self.view.refresh_notes_list()

    def observer_notes_db_synced_note(self, notes_db, evt_type, evt: events.NoteSyncedEvent):
        """This observer gets called only when a note returns from
        a sync that's more recent than our most recent mod to that note.
        """

        # if the note synced back matches our currently selected note,
        # we overwrite.
        if self.selected_note_key is not None and self.selected_note_key == evt.lkey:
            selected_note_o = self.notes_list_model.get(self.selected_note_key)
            content = self.notes_db.get_note_content(evt.lkey)
            if selected_note_o.note['content'] != content:
                self.view.mute_note_data_changes()
                # in this case, we want to keep the user's undo buffer so that they
                # can undo synced back changes if they would want to.
                self.view.set_note_data(selected_note_o.note, reset_undo=False)
                self.view.unmute_note_data_changes()
        self.view.refresh_notes_list()

    def observer_view_click_notelink(self, view, evt_type, note_name: str):
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

    def observer_view_delete_note(self, view, evt_type, evt: events.NoteSelectionChangedEvent):
        # delete note from notes_db
        # remove the note from the notes_list_model.list

        # first get key of note that is to be deleted
        key = self.selected_note_key

        # then try to select after the one that is to be deleted
        nidx = evt.sel + 1
        if 0 <= nidx < self.view.get_number_of_notes():
            self.view.select_note(nidx)

        # finally delete the note
        self.notes_db.delete_note(key)

        # and refresh the window.
        self.view.refresh_notes_list()

    def helper_markdown_to_html(self):
        if self.selected_note_key:
            key = self.selected_note_key
            c = self.notes_db.get_note_content(key)
            logging.debug("Trying to convert %s to html." % (key, ))
            if HAVE_MARKDOWN:
                logging.debug("Convert note %s to html." % (key, ))
                exts = re.split('\s+', self.config.md_extensions.strip()) if self.config.md_extensions else []
                exts += list(DEFAULT_MARKDOWN_EXTS)
                # remove duplicate items on exts.
                exts = list(set(exts))

                html = markdown.markdown(c, extensions=exts)
                logging.debug("Convert done.")
                if self.config.md_css_path:
                    css = u"""<link rel="stylesheet" href="%s">""" % (self.config.md_css_path, )
                    html = u"""<div class="markdown-body">%s</div>""" % (html, )
                else:
                    css = u""""""

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
%s
</head>
<body>
%s
</body>
</html>
            """ % (
                '<meta http-equiv="refresh" content="5">' if self.view.get_continuous_rendering() else "",
                css if self.config.md_css_path else "",
                html,
            )
            f.write(s)
            f.close()
            return fn

    def helper_rest_to_html(self):
        if self.selected_note_key:
            key = self.selected_note_key
            c = self.notes_db.get_note_content(key)
            if HAVE_DOCUTILS:
                settings = {}
                if self.config.rest_css_path:
                    settings['stylesheet_path'] = self.config.rest_css_path
                # this gives the whole document
                html: bytes = docutils.core.publish_string(c, writer_name='html', settings_overrides=settings)
                # publish_parts("*anurag*",writer_name='html')['body']
                # gives just the desired part of the tree

            else:
                html = b"<p>python docutils not installed, required for rendering reST to HTML.</p>"
                html += b"<p>Please install with \"pip install docutils\".</p>"

            # create filename based on key
            fn = os.path.join(self.config.db_path, key + '_rest.html')
            with open(fn, mode='wb') as f:
                f.write(html)
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

        savet = 'Saving %d notes.' % (saven, ) if saven > 0 else ''
        synct = 'Waiting to sync %d notes.' % (syncn, ) if syncn > 0 else ''
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

    def observer_view_select_note(self, view, evt_type, evt: events.NoteSelectionChangedEvent):
        self.select_note(evt.sel)

    def observer_view_sync_current_note(self, view, evt_type, evt):
        if self.selected_note_key:
            key = self.selected_note_key
            # this call will update our in-memory version if necessary
            ret = self.notes_db.sync_note_unthreaded(key)
            if ret and ret[1] == True:
                self.view.update_selected_note_data(self.notes_db.notes[key])
                self.view.set_status_text('Synced updated note from server.')

            elif ret and ret[1] == False:
                self.view.set_status_text('Server had nothing newer for this note.')

            elif ret is None:
                self.view.set_status_text('Unable to sync with server. Offline?')

    def observer_view_change_cs(self, view, evt_type, evt: events.CheckboxChangedEvent):
        # evt.value is the new value
        # only do something if user has really toggled
        if evt.value != self.config.case_sensitive:
            self.config.case_sensitive = evt.value
            self.view.refresh_notes_list()

    def observer_view_change_search_mode(self, view, evt_type, evt: events.TextBoxChangedEvent):
        if evt.value != self.config.search_mode:
            self.config.search_mode = evt.value
            self.view.refresh_notes_list()

    def observer_view_change_entry(self, view, evt_type, evt: events.TextBoxChangedEvent):
        # store the currently selected note key
        k = self.selected_note_key
        # for each new evt.value coming in, get a new list from the notes_db
        # and set it in the notes_list_model
        nn, match_regexp, active_notes = self.notes_db.filter_notes(evt.value)
        self.notes_list_model.match_regexp = match_regexp
        self.notes_list_model.set_list(nn)
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

            # see if the note has been updated (content, tags, pin)
            new_note = self.notes_db.get_note(k)

            # check if the currently selected note is different from the one
            # currently being displayed. this could happen if a sync gets
            # a new note of the server to replace the currently displayed one.
            if self.view.is_note_different(new_note):
                logging.debug("Currently selected note %s replaced by newer from server." % (k, ))
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
        if self.selected_note_key:
            self.notes_db.set_note_content(self.selected_note_key, self.view.get_text())

    def observer_view_delete_tag(self, view, evt_type, evt: events.TagRemovedEvent):
        self.notes_db.delete_note_tag(self.selected_note_key, evt.tag)
        self.view.cmd_notes_list_select()

    def observer_view_add_tag(self, view, evt_type, evt: events.TagsAddedEvent):
        self.notes_db.add_note_tags(self.selected_note_key, evt.tags)
        self.view.cmd_notes_list_select()
        self.view.tags_entry_var.set('')

    def observer_view_change_pinned(self, view, evt_type, evt: events.CheckboxChangedEvent):
        # get new text and update our database
        if self.selected_note_key:
            self.notes_db.set_note_pinned(self.selected_note_key, evt.value)

    def observer_view_change_sort_mode(self, view, evt_type, evt: events.SortModeChangedEvent):
        self.config.sort_mode = evt.mode
        # Refresh notes list.
        self.view.refresh_notes_list()

    def observer_view_change_pinned_on_top(self, view, evt_type, evt: events.PinnedOnTopChangedEvent):
        self.config.pinned_ontop = evt.pinned_on_top
        self.view.refresh_notes_list()

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
            if self.config.confirm_exit:
                msg = "Do you want to exit?"
                if not self.view.askyesno('Confirm exit', msg):
                    return

            self.view.close()

    def observer_view_create_note(self, view, evt_type, evt: events.NoteCreatedEvent):
        # create the note
        new_key = self.notes_db.create_note(evt.title)
        # clear the search entry, this should trigger a new list being returned
        keyword = ''
        if self.config.keep_search_keyword:
            keyword = self.view.get_search_entry_text()
        self.view.set_search_entry_text(keyword)
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
            # no note selected, so we clear the UI (and display a clear
            # message that no note is selected) and we disable note
            # editing controls.
            self.view.clear_note_ui()
            self.view.set_note_editing(False)

        self.selected_note_key = key

        # when we do this, we don't want the change:{text,tags,pinned} events
        # because those should only fire when they are changed through the UI
        self.view.mute_note_data_changes()
        self.view.set_note_data(note)
        if key:
            self.view.set_note_status(self.notes_db.get_note_status(key))

        self.view.unmute_note_data_changes()

    def sync_full(self):
        self.notes_db.sync_full_threaded()

    def update_note_status(self):
        skey = self.selected_note_key
        self.view.set_note_status(self.notes_db.get_note_status(skey))


def get_appdir():
    # setup appdir
    if hasattr(sys, 'frozen') and sys.frozen:
        if hasattr(sys, '_MEIPASS'):
            # PyInstaller
            appdir = sys._MEIPASS

            # WORKAROUND: Bug that always raise the SSLCertVerificationError from urlopen()
            #             when CPython is not installed.

            # Use certificate from certifi only if cafile could not find by ssl.
            # See https://github.com/pyinstaller/pyinstaller/pull/3952
            import ssl
            if ssl.get_default_verify_paths().cafile is None:
                import certifi.core
                os.environ['SSL_CERT_FILE'] = certifi.core.where()
        else:
            # py2exe
            appdir, _ = os.path.split(sys.executable)

    else:
        dirname, _ = os.path.split(os.path.realpath(__file__))
        if dirname and dirname != os.curdir:
            appdir = dirname
        else:
            appdir = os.getcwd()

    # make sure it's the full path
    appdir_full_path = os.path.abspath(appdir)
    return appdir_full_path


def parse_cmd_line_args(args: typing.Optional[typing.List] = None) -> argparse.Namespace:
    """ Parse command line arguments

    Args:
        args: List of command line arguments. If args is not specified, takes args from sys.args.

    Returns:
        A namespace object generated by argparse.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--cfg', '-c', dest='cfg', type=pathlib.Path, metavar='nvpy.cfg', help='path to config file')
    return parser.parse_args(args)


@contextlib.contextmanager
def profiler_context(fname_prefix: str):
    """ Enable profiler insider context.
    When leave the context, writes result to file as two formats (binary and text).
    """
    try:
        import cProfile as profile
    except:
        import profile  # type:ignore
    import pstats

    p = profile.Profile()
    p.enable()
    yield
    p.disable()

    # Write result to files.
    prefix = f'{fname_prefix}.{time.time_ns()}.{os.getpid()}'
    text_file = f'{prefix}.txt'
    bin_file = f'{prefix}.bin'
    with open(text_file, 'w') as f:
        s = pstats.Stats(p, stream=f)
        s.dump_stats(bin_file)
        s.sort_stats(pstats.SortKey.TIME, pstats.SortKey.CUMULATIVE, pstats.SortKey.CALLS)
        # The stream=f argument specified to constructor. print_* functions writes to f instead of stdout.
        s.print_stats()


@contextlib.contextmanager
def nullcontext():
    #  WORKAROUND: Python 3.6 does not have the contextlib.nullcontext.
    #  If the minimum requirement is Python >3.7, we can remove it.
    yield


def main(args: typing.Optional[typing.List] = None):
    ns = parse_cmd_line_args(args)
    cfg_files = None
    if ns.cfg is not None:
        cfg_files = [ns.cfg]
    config = Config(get_appdir(), cfg_files)

    # Setup profiler.
    profiler: typing.ContextManager = nullcontext()
    if config.use_profiler:
        prefix = str(pathlib.Path(config.db_path) / 'nvpy-profile')
        profiler = profiler_context(prefix)

    try:
        with profiler:
            controller = Controller(config)
            controller.main_loop()
    except tk.Ucs4NotSupportedError as e:
        logging.error(str(e))
        import tkMessageBox  # type:ignore
        tkMessageBox.showerror('UCS-4 not supported', str(e))
        raise


if __name__ == '__main__':
    main()
