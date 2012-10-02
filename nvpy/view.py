# nvPY: cross-platform note-taking app with simplenote syncing
# copyright 2012 by Charl P. Botha <cpbotha@vxlabs.com>
# new BSD license

import copy
import logging
import os
import re
import search_entry
import sys
import tk
import tkFont
import tkMessageBox
import utils
import webbrowser

from datetime import datetime

class WidgetRedirector:

    """Support for redirecting arbitrary widget subcommands."""

    def __init__(self, widget):
        self.dict = {}
        self.widget = widget
        self.tk = tk = widget.tk
        w = widget._w
        self.orig = w + "_orig"
        tk.call("rename", w, self.orig)
        tk.createcommand(w, self.dispatch)

    def __repr__(self):
        return "WidgetRedirector(%s<%s>)" % (self.widget.__class__.__name__,
                                             self.widget._w)

    def close(self):
        for name in self.dict.keys():
            self.unregister(name)
        widget = self.widget; del self.widget
        orig = self.orig; del self.orig
        tk = widget.tk
        w = widget._w
        tk.deletecommand(w)
        tk.call("rename", orig, w)

    def register(self, name, function):
        if self.dict.has_key(name):
            previous = dict[name]
        else:
            previous = OriginalCommand(self, name)
        self.dict[name] = function
        setattr(self.widget, name, function)
        return previous

    def unregister(self, name):
        if self.dict.has_key(name):
            function = self.dict[name]
            del self.dict[name]
            if hasattr(self.widget, name):
                delattr(self.widget, name)
            return function
        else:
            return None

    def dispatch(self, cmd, *args):
        m = self.dict.get(cmd)
        try:
            if m:
                return m(*args)
            else:
                return self.tk.call((self.orig, cmd) + args)
        except tk.TclError:
            return ""


class OriginalCommand:

    def __init__(self, redir, name):
        self.redir = redir
        self.name = name
        self.tk = redir.tk
        self.orig = redir.orig
        self.tk_call = self.tk.call
        self.orig_and_name = (self.orig, self.name)

    def __repr__(self):
        return "OriginalCommand(%r, %r)" % (self.redir, self.name)

    def __call__(self, *args):
        return self.tk_call(self.orig_and_name + args)


#########################################################################
class RedirectedText(tk.Text):
    """We would like to know when the Text widget's contents change.  We can't
    just override the insert method, we have to make use of some Tk magic.
    This magic is encapsulated in the idlelib.WidgetRedirector class which
    we use here.
    """

    def __init__(self, master=None, cnf={}, **kw):
        tk.Text.__init__(self, master, cnf, **kw)

        # now attach the redirector
        self.redir = WidgetRedirector(self)
        self.orig_insert = self.redir.register("insert", self.new_insert)
        self.orig_delete = self.redir.register("delete", self.new_delete)

    def new_insert(self, *args):
        self.orig_insert(*args)
        self.event_generate('<<Change>>')

    def new_delete(self, *args):
        self.orig_delete(*args)
        self.event_generate('<<Change>>')

#########################################################################
class StatusBar(tk.Frame):
    """Adapted from the tkinterbook.
    """
    
    # actions
    # global status
    # note status

    def __init__(self, master):
        tk.Frame.__init__(self, master)
        
        self.status = tk.Label(self, relief=tk.SUNKEN, anchor=tk.W)
        #self.label.pack(fill=tk.X)
        self.status.pack(side=tk.LEFT, fill=tk.X, expand=1)
        
        self.note_status = tk.Label(self, relief=tk.SUNKEN, anchor=tk.W)
        self.note_status.pack(side=tk.LEFT, fill=tk.X)
        
    def set_note_status(self, fmt, *args):
        """ *.. .s. .sS
        """ 
        self.note_status.config(text=fmt % args)
        self.note_status.update_idletasks()

    def set_status(self, fmt, *args):
        self.status.config(text=fmt % args)
        self.status.update_idletasks()

    def clear_status(self):
        self.status.config(text="")
        self.status.update_idletasks()

class NotesList(tk.Frame):
    """
    @ivar note_headers: list containing tuples with each note's title, tags,
    modified date and so forth. Always in sync with what is displayed.
    """

    TITLE_COL = 0
    TAGS_COL = 1
    MODIFYDATE_COL = 2
    PINNED_COL = 3

    def __init__(self, master, font_family, font_size, background_color):
        tk.Frame.__init__(self, master)

        yscrollbar = tk.Scrollbar(self)
        yscrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        f = tkFont.Font(family=font_family, size=font_size)
        # tkFont.families(root) returns list of available font family names
        # this determines the width of the complete interface (yes)
        # size=-self.config.font_size
        self.text = tk.Text(self, height=25, width=30,
            wrap=tk.NONE,
            font=f,
            yscrollcommand=yscrollbar.set,
            undo=True,
            background = background_color)
        # change default font at runtime with:
        #text.config(font=f)

        self.text.config(cursor="arrow")
        self.disable_text()
        self.text.pack(fill=tk.BOTH, expand=1)

        # tags for all kinds of styling ############################
        ############################################################

        self.text.tag_config("selected", background="light blue")

        self.text.tag_config("pinned", foreground="dark gray")

        # next two lines from:
        # http://stackoverflow.com/a/9901862/532513
        bold_font = tkFont.Font(self.text, self.text.cget("font"))
        bold_font.configure(weight="bold")
        self.text.tag_config("title", font=bold_font)

        italic_font = tkFont.Font(self.text, self.text.cget("font"))
        italic_font.configure(slant="italic")
        self.text.tag_config("tags", font=italic_font, foreground="dark gray")
        self.text.tag_config("found", font=italic_font, foreground="dark gray", background="lightyellow")

        self.text.tag_config("modifydate", foreground="dark gray")

        yscrollbar.config(command=self.text.yview)

        self._bind_events()

        self.selected_idx = -1
        # list containing tuples with each note's title, tags,
        self.note_headers = []

    def append(self, note, config):
        """
        @param note: The complete note dictionary.
        """


        title = utils.get_note_title(note)
        tags = note.get('tags')
        modifydate = float(note.get('modifydate'))
        pinned = utils.note_pinned(note)
        self.note_headers.append((title, tags, modifydate, pinned))

        self.enable_text()


        self.text.insert(tk.END, title, ("title,"))

        if pinned:
            self.text.insert(tk.END, ' *', ("pinned",))

        self.text.insert(tk.END, ' ' + utils.human_date(modifydate), ("modifydate",))

        # tags can be None (newly created note) or [] or ['tag1', 'tag2']
        if tags > 0:
            if config.tagfound:
                self.text.insert(tk.END, ' ' + ','.join(tags), ("found",))
            else:
                self.text.insert(tk.END, ' ' + ','.join(tags), ("tags",))


        self.text.insert(tk.END, '\n')

        self.disable_text()

    def _bind_events(self):
        # Text widget events ##########################################


        self.text.bind("<Button 1>", self.cmd_text_button1)

        # same deal as for pageup
        # we have to stop the text widget class event handler from firing
        def cmd_up(e):
            self.select_prev(silent=False)
            return "break"

        self.text.bind("<Up>", cmd_up)

        # for pageup, event handler needs to return "break" so that
        # Text widget's default class handler for pageup does not trigger.
        def cmd_pageup(e):
            self.select_prev(silent=False, delta=10)
            return "break"

        self.text.bind("<Prior>", cmd_pageup)

        def cmd_down(e):
            self.select_next(silent=False)
            return "break"

        self.text.bind("<Down>", cmd_down)

        def cmd_pagedown(e):
            self.select_next(silent=False, delta=10)
            return "break"

        self.text.bind("<Next>", cmd_pagedown)


    def cmd_text_button1(self, event):
        # find line that was clicked on
        text_index = self.text.index("@%d,%d" % (event.x, event.y))
        # go from event coordinate to tkinter text INDEX to note idx!
        idx = int(text_index.split('.')[0]) - 1
        self.select(idx, silent=False)


    def clear(self):
        """

        """
        self.enable_text()
        # clear everything from the display
        self.text.delete(1.0, tk.END)
        # and make sure our backing store is in sync
        del self.note_headers[:]
        self.disable_text()

    def disable_text(self):
        self.text.config(state=tk.DISABLED)

    def enable_text(self):
        self.text.config(state=tk.NORMAL)

    def find_note_by_title(self, title):
        """
        Find note with given title.

        @returns: Note index if found, -1 otherwise.
        """

        idx = -1
        for i, nh in enumerate(self.note_headers):
            t = nh[NotesList.TITLE_COL]
            if t == title:
                idx = i
                break

        return idx

    def get_number_of_notes(self):
        # could also have used:
        # return int(self.text.index('end-1c').split('.')[0])
        # but we have the backing store!
        return len(self.note_headers)

    def get_pinned(self, idx):
        return self.note_headers[idx][NotesList.PINNED_COL]

    def get_tags(self, idx):
        """
        @returns: raw list of tag strings, e.g. ['work', 'howto']
        """
        return self.note_headers[idx][NotesList.TAGS_COL]

    def get_title(self, idx):
        return self.note_headers[idx][NotesList.TITLE_COL]

    def get_modifydate(self, idx):
        """
        Return modifydate of idx'th note.

        @returns: modifydate as a floating point timestamp.
        """
        return self.note_headers[idx][NotesList.MODIFYDATE_COL]

    def idx_to_index_range(self, idx):
        """
        Given a note index idx, return the Tkinter text index range for
        the start and end of that note.
        """

        # tkinter text first line is 1, but first column is 0
        row = idx+1
        start = "%d.0" % (row,)
        end = "%d.end" % (row,)

        return (start, end)

    def select(self, idx, silent=True):
        """
        @param idx: index of note to select. -1 if no selection.
        """

        # remove tag selected from row 1 (first) and column 0 to the end of the buffer
        self.text.tag_remove("selected", "1.0", "end")

        if idx >= 0 and idx < self.get_number_of_notes():
            # then add it to the requested note line(s)
            start, end = self.idx_to_index_range(idx)
            self.text.tag_add("selected", start, end)
            # ensure that this is visible
            self.text.see(start)
            # and store the current idx
            self.selected_idx = idx

        else:
            self.selected_idx = -1

        if not silent:
            self.event_generate('<<NotesListSelect>>')

    def select_next(self, silent=True, delta=1):
        """
        Select note right after the current selection.
        """

        new_idx = self.selected_idx + delta
        if new_idx >= 0 and new_idx < self.get_number_of_notes():
            self.select(new_idx, silent)

        elif new_idx >= self.get_number_of_notes():
            self.select(self.get_number_of_notes() - 1, silent)

    def select_prev(self, silent=True, delta=1):
        """
        Select note right after the current selection.
        """

        new_idx = self.selected_idx - delta
        if new_idx >= 0 and new_idx <= self.get_number_of_notes():
            self.select(new_idx, silent)

        elif new_idx < 0:
            self.select(0, silent)

tkinter_umlauts=['odiaeresis', 'adiaeresis', 'udiaeresis', 'Odiaeresis', 'Adiaeresis', 'Udiaeresis', 'ssharp']

class TriggeredcompleteEntry(tk.Entry):
    """
    Subclass of tk.Entry that features triggeredcompletion.

    How this works: User types first part of tag, then triggers complete with
    ctrl-space. The first matching tag is shown. The user can either continue
    pressing ctrl-space to see more matching tags, or right arrow to select
    the current suggestion and continue typing. Backspace will delete the
    suggested part. Left arrow will delete the last character with the cursor
    at the end of the line, or the suggested part if not.

    To enable triggeredcompletion use set_completion_list(list) to define 
    a list of possible strings to hit.
    To cycle through hits use CTRL <space> keys.

    @ivar cycle: if 1, then we're cycling through alternative completions.
    """

    def __init__(self, master, case_sensitive, **kw): 
        tk.Entry.__init__(self, master, **kw)
        self.case_sensitive = case_sensitive
        self.bind('<KeyRelease>', self.handle_keyrelease)               

    def set_completion_list(self, completion_list):
        self._completion_list = completion_list
        self._hits = []
        self._hit_index = 0
        self.position = 0
        self.cycle = 0

    def triggeredcomplete(self):
        """triggeredcomplete the Entry, delta may be 0/1 to cycle through possible hits"""

        if self.cycle: # need to delete selection otherwise we would fix the current position
            self.delete(self.position, tk.END)
            self._hit_index += 1
            if self._hit_index == len(self._hits):
                self._hit_index = 0

        else: # set position to end so selection starts where textentry ended
            self.position = len(self.get())
            # collect hits
            _hits = []
            for element in self._completion_list:
                if self.case_sensitive == 0: 
                    if element.lower().startswith(self.get().lower()):
                         _hits.append(element)
                else:
                    if element.startswith(self.get()):
                         _hits.append(element)

            self._hit_index = 0
            self._hits=_hits

        # now finally perform the triggered completion
        if self._hits:
            self.delete(0,tk.END)
            self.insert(0,self._hits[self._hit_index])
            self.select_range(self.position,tk.END)

    def handle_keyrelease(self, event):
        """event handler for the keyrelease event on this widget"""
        ctrl  = ((event.state & 0x0004) != 0)

        # special case handling below only if we are in cycle mode.
        if self.cycle:
            if event.keysym == "BackSpace":
                self.cycle = 0
                self.delete(self.index(tk.INSERT), tk.END)
                self.position = self.index(tk.END)

            if event.keysym == "Left":
                self.cycle = 0
                if self.position < self.index(tk.END): # delete the selection
                    self.delete(self.position, tk.END)

                else:
                    self.position = self.position-1 # delete one character
                    self.delete(self.position, tk.END)

            if event.keysym == "Right":
                self.position = self.index(tk.END) # go to end (no selection)
                self.cycle = 0

        if event.keysym == "space" and ctrl:
            # cycle 
            self.triggeredcomplete()
            if self.cycle == 0:
                self.cycle = 1


class View(utils.SubjectMixin):
    """Main user interface class.
    """
    
    def __init__(self, config, notes_list_model):
        utils.SubjectMixin.__init__(self)
        
        self.config = config
        self.taglist = []
        
        notes_list_model.add_observer('set:list', self.observer_notes_list)
        self.notes_list_model = notes_list_model
        
        self.root = None

        self._create_ui()
        self._bind_events()
        
        self.text_tags_links = []
        self.text_tags_search = []

        #self._current_text = None
        #self.user_text.focus_set()

        self.search_entry.focus_set()

    def askyesno(self, title, msg):
        return tkMessageBox.askyesno(title, msg)
    
    def cmd_notes_list_select(self, evt):
        sidx = self.notes_list.selected_idx
        self.notify_observers('select:note', utils.KeyValueObject(sel=sidx))
        
    def cmd_root_delete(self, evt=None):
        sidx = self.notes_list.selected_idx
        self.notify_observers('delete:note', utils.KeyValueObject(sel=sidx))
        
    def cmd_root_new(self, evt=None):
        # this'll get caught by a controller event handler
        self.notify_observers('create:note', utils.KeyValueObject(title=self.get_search_entry_text()))
        # the note will be created synchronously, so we can focus the text area already
        self.text_note.focus()

    def cmd_select_all(self, evt=None):
        self.text_note.tag_add("sel", "1.0", "end-1c")
        # we don't want the text bind_class() handler for Ctrl-A to be fired.
        return "break"

    def get_continuous_rendering(self):
        return self.continuous_rendering.get()

    def get_selected_text(self):
        """
        Return note text that has been selected by user.
        """

        try:
            return self.text_note.selection_get()
        except tk.TclError:
            return ''

    def get_text(self):
        # err, you have to specify 1.0 to END, and NOT 0 to END like I thought.
        # also, see the comment by Bryan Oakley to
        # http://stackoverflow.com/a/3137169
        # we need to get rid of newline that text adds automatically
        # at end.
        return self.text_note.get(1.0, "end-1c")
    
    def get_search_entry_text(self):
        return self.search_entry_var.get()
    
    def refresh_notes_list(self):
        """Trigger a complete refresh notes list by resetting search entry.
        """
        # store cursor position first! returns e.g. 8.32
        #cursor_pos = self.text_note.index(tk.INSERT)
        
        # since 0.6, set_search_entry() tries to leave the currently selected
        # note untouched if it still exists in the newly returned list
        # so we don't have to do an explicit reselect.
        self.set_search_entry_text(self.get_search_entry_text())
        
        #self.text_note.mark_set(tk.INSERT, cursor_pos)

    def see_first_search_instance(self):
        """If there are instances of the search string in the current
        note, ensure that the first one is visible.
        """

        if self.text_tags_search:
            self.text_note.see(self.text_tags_search[0] + '.first')

    def select_note(self, idx, silent=False):
        """Programmatically select the note by idx

        @param silent: If this is True, don't fire an event. VERY
        IMPORTANT: if you use silent, the controller won't set the
        selected_note_idx. You should make sure that it's in sync with
        what you've just selected.
        """

        self.notes_list.select(idx, silent)

    def select_note_by_name(self, name):
        idx = self.notes_list.find_note_by_title(name)
        if idx >= 0:
            self.select_note(idx, silent=False)

        return idx

    def set_note_status(self, status):
        """status is an object with ivars modified, saved and synced.
        """
        
        if status.modified:
            s = 'modified'
        elif status.saved and status.synced:
            s = 'saved and synced'
        elif status.saved:
            s = 'saved'
        else:
            s = 'synced'
        
        self.statusbar.set_note_status('Note is %s' % (s,))
            
    def set_search_entry_text(self, text):
        self.search_entry_var.set(text)
        
    def _bind_events(self):
        # make sure window close also goes through our handler
        self.root.protocol('WM_DELETE_WINDOW', self.handler_close)

        self.root.bind_all("<Control-g>", lambda e: self.tags_entry.focus())
        
        self.notes_list.bind("<<NotesListSelect>>", self.cmd_notes_list_select)
        # same behaviour as when the user presses enter on search entry:
        # if something is selected, focus the text area
        # if nothing is selected, try to create new note with
        # search entry value as name
        self.notes_list.text.bind("<Return>", self.handler_search_enter)
        
        self.search_entry.bind("<Escape>", lambda e:
                self.search_entry.delete(0, tk.END))
        # this will either focus current content, or
        # if there's no selection, create a new note.
        self.search_entry.bind("<Return>", self.handler_search_enter)
        
        self.search_entry.bind("<Up>", lambda e:
            self.notes_list.select_prev(silent=False))
        self.search_entry.bind("<Prior>", lambda e:
            self.notes_list.select_prev(silent=False, delta=10))

        self.search_entry.bind("<Down>", lambda e:
            self.notes_list.select_next(silent=False))
        self.search_entry.bind("<Next>", lambda e:
            self.notes_list.select_next(silent=False, delta=10))

        self.text_note.bind("<<Change>>", self.handler_text_change)
        
        # user presses escape in text area, they go back to notes list
        self.text_note.bind("<Escape>", lambda e: self.notes_list.text.focus())
        # <Key>
        
        self.text_note.bind("<Control-a>", self.cmd_select_all)

        self.tags_entry_var.trace('w', self.handler_tags_entry)
        self.tags_entry.bind("<Escape>", lambda e: self.text_note.focus())

        self.pinned_checkbutton_var.trace('w', self.handler_pinned_checkbutton)

        self.root.after(self.config.housekeeping_interval_ms, self.handler_housekeeper)

    def _create_menu(self):
        """Utility function to setup main menu.

        Called by _create_ui.
        """
        
        # MAIN MENU ####################################################
        menu = tk.Menu(self.root)
        self.root.config(menu=menu)

        file_menu = tk.Menu(menu, tearoff=False)
        menu.add_cascade(label="File", underline='0', menu=file_menu)
        
        
        
        

        # FILE ##########################################################
        file_menu.add_command(label = "New note", underline=0,
                              command=self.cmd_root_new, accelerator="Ctrl+N")
        self.root.bind_all("<Control-n>", self.cmd_root_new)

        file_menu.add_command(label = "Delete note", underline=0,
                              command=self.cmd_root_delete, accelerator="Ctrl+D")        
        self.root.bind_all("<Control-d>", self.cmd_root_delete)
        
        file_menu.add_separator()
        
        file_menu.add_command(label = "Sync full", underline=5,
                              command=self.cmd_sync_full)
        file_menu.add_command(label = "Sync current note",
                underline=0, command=self.cmd_sync_current_note,
                accelerator="Ctrl+S")
        self.root.bind_all("<Control-s>", self.cmd_sync_current_note)
        
        file_menu.add_separator()

        file_menu.add_command(label = "Render Markdown to HTML", underline=7,
                command=self.cmd_markdown, accelerator="Ctrl+M")
        self.root.bind_all("<Control-m>", self.cmd_markdown)

        self.continuous_rendering = tk.BooleanVar()
        self.continuous_rendering.set(False)
        file_menu.add_checkbutton(label="Continuous Markdown to HTML rendering",
                onvalue=True, offvalue=False,
                variable=self.continuous_rendering)

        file_menu.add_command(label = "Render reST to HTML", underline=7,
                command=self.cmd_rest, accelerator="Ctrl+R")
        self.root.bind_all("<Control-r>", self.cmd_rest)
        
        file_menu.add_separator()

        file_menu.add_command(label = "Exit", underline=1,
                              command=self.handler_close, accelerator="Ctrl+Q")
        self.root.bind_all("<Control-q>", self.handler_close)

        # EDIT ##########################################################
        edit_menu = tk.Menu(menu, tearoff=False)
        menu.add_cascade(label="Edit", underline=0, menu=edit_menu)
        
        edit_menu.add_command(label="Undo", accelerator="Ctrl+Z",
                              underline=0, command=lambda: self.text_note.edit_undo())
        self.root.bind_all("<Control-z>", lambda e: self.text_note.edit_undo())
        
        edit_menu.add_command(label="Redo", accelerator="Ctrl+Y",
                              underline=0, command=lambda: self.text_note.edit_undo())
        self.root.bind_all("<Control-y>", lambda e: self.text_note.edit_redo())
                
        
        edit_menu.add_separator()
        
        edit_menu.add_command(label="Cut", accelerator="Ctrl+X",
                              underline=2, command=self.cmd_cut)
        edit_menu.add_command(label="Copy", accelerator="Ctrl+C",
                              underline=0, command=self.cmd_copy)
        edit_menu.add_command(label="Paste", accelerator="Ctrl+V",
                              underline=0, command=self.cmd_paste)

        edit_menu.add_command(label="Select All", accelerator="Ctrl+A",
                              underline=7, command=self.cmd_select_all)
        # FIXME: ctrl-a is usually bound to start-of-line. What's a
        # better binding for select all then?

        edit_menu.add_separator()
        
        edit_menu.add_command(label="Find", accelerator="Ctrl+F",
                              underline=0, command=lambda: self.search_entry.focus())
        self.root.bind_all("<Control-f>", lambda e: self.search_entry.focus())

        # TOOLS ########################################################
        tools_menu = tk.Menu(menu, tearoff=False)
        menu.add_cascade(label="Tools", underline=0, menu=tools_menu)

        tools_menu.add_command(label="Word Count",
            underline=0, command=self.word_count)

        # the internet thinks that multiple modifiers should work, but this didn't
        # want to.
        #self.root.bind_all("<Control-Shift-c>", lambda e: self.word_count())

        # HELP ##########################################################
        help_menu = tk.Menu(menu, tearoff=False)
        menu.add_cascade(label="Help", underline='0', menu=help_menu)

        help_menu.add_command(label = "About", underline = 0,
                              command = self.cmd_help_about)

        # END MENU ######################################################

    def _create_ui(self):

        # these two variables determine the final dimensions of our interface
        #FRAME_HEIGHT=400
        TEXT_WIDTH=80

        # set the correct class name. this helps your desktop environment
        # to identify the nvPY window.
        self.root = tk.Tk(className="nvPY")

        self.root.title("nvPY")
        #self.root.configure(background="#b2b2b2")

        # with iconphoto we have to use gif, also on windows
        icon_fn = 'nvpy.gif'

        iconpath = os.path.join(
            self.config.app_dir, 'icons', icon_fn)

        self.icon = tk.PhotoImage(file=iconpath)
        self.root.tk.call('wm', 'iconphoto', self.root._w, self.icon)

        # create menu ###################################################
        self._create_menu()

        # separator after menu ##########################################
        #separator = tk.Frame(self.root, height=2, bd=1, relief=tk.SUNKEN)
        #separator.pack(fill=tk.X, padx=5, pady=2, side=tk.TOP)

        # setup statusbar ###############################################
        # first pack this before panedwindow, else behaviour is unexpected
        # during sash moving and resizing
        self.statusbar = StatusBar(self.root)
        self.statusbar.set_status('%s', 'Welcome to nvPY!')
        self.statusbar.pack(fill=tk.X, side=tk.BOTTOM)

        search_frame = tk.Frame(self.root)
        
        search_entry.make_style()
        self.search_entry_var = tk.StringVar()
        #self.search_entry = tk.Entry(search_frame, textvariable=self.search_entry_var, style="Search.entry")
        self.search_entry = TriggeredcompleteEntry(search_frame, self.config.case_sensitive, textvariable=self.search_entry_var, style="Search.entry")
        #self.search_entry.set_completion_list(self.taglist)
        self.search_entry_var.trace('w', self.handler_search_entry)
        self.search_entry.pack(fill=tk.X,padx=5, pady=5)
        search_frame.pack(side=tk.TOP, fill=tk.X)
        
        
        # the paned window ##############################################
        paned_window = tk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=1)
        
        left_frame = tk.Frame(paned_window, width=100)
        paned_window.add(left_frame)

        self.notes_list = NotesList(
            left_frame,
            self.config.list_font_family, self.config.list_font_size, self.config.background_color)
        self.notes_list.pack(fill=tk.BOTH, expand=1)

        right_frame = tk.Frame(paned_window, width=400)
        paned_window.add(right_frame)

        note_meta_frame = tk.Frame(right_frame)
        note_meta_frame.pack(side=tk.BOTTOM, fill=tk.X)

        pinned_label = tk.Label(note_meta_frame,text="Pinned")
        pinned_label.pack(side=tk.LEFT)
        self.pinned_checkbutton_var = tk.IntVar()
        pinned_checkbutton = tk.Checkbutton(note_meta_frame, variable=self.pinned_checkbutton_var)
        pinned_checkbutton.pack(side=tk.LEFT)

        tags_label = tk.Label(note_meta_frame, text="Tags")
        tags_label.pack(side=tk.LEFT)
        self.tags_entry_var = tk.StringVar()
        self.tags_entry = tk.Entry(note_meta_frame, textvariable=self.tags_entry_var)
        self.tags_entry.pack(side=tk.LEFT, fill=tk.X, expand=1, pady=3, padx=3)


        # we'll use this method to create the different edit boxes
        def create_scrolled_text(master):
            yscrollbar = tk.Scrollbar(master)
            yscrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            #f = tkFont.nametofont('TkFixedFont')
            f = tkFont.Font(family=self.config.font_family, size=-self.config.font_size)
            # tkFont.families(root) returns list of available font family names
            # this determines the width of the complete interface (yes)
            text = RedirectedText(master, height=25, width=TEXT_WIDTH,
                                  wrap=tk.WORD,
                                  font=f, tabs=(4 * f.measure(0), 'left'), tabstyle='wordprocessor',
                                  yscrollcommand=yscrollbar.set,
                                  undo=True,
                                  background = self.config.background_color)
            # change default font at runtime with:
            text.config(font=f)

            text.pack(fill=tk.BOTH, expand=1)

            #xscrollbar.config(command=text.xview)
            yscrollbar.config(command=text.yview)

            return text


        # setup user_text ###############################################
        self.text_note = create_scrolled_text(right_frame)


        # finish UI creation ###########################################

        # now set the minsize so that things can not disappear
        self.root.minsize(self.root.winfo_width(), self.root.winfo_height())
        
        # call update so we know that sizes are up to date
        self.root.update_idletasks()

    def get_number_of_notes(self):
        return self.notes_list.get_number_of_notes()

    def handler_close(self, evt=None):
        """Handler for exit menu command and close window event.
        """
        self.notify_observers('close', None)
        
    def close(self):
        """Programmatically close application windows.
        
        Called by controller. 
        """
        self.root.destroy()

    def cmd_cut(self):
        self.text_note.event_generate('<<Cut>>')

    def cmd_copy(self):
        self.text_note.event_generate('<<Copy>>')

    def cmd_markdown(self, event=None):
        self.notify_observers('command:markdown', None)
        
    def cmd_paste(self):
        self.text_note.event_generate('<<Paste>>')


    def cmd_help_about(self):
        tkMessageBox.showinfo(
            'Help | About',
            'nvPY %s is copyright 2012 by Charl P. Botha '
            '<http://charlbotha.com/>\n\n'
            'A rather ugly but cross-platform simplenote client.' % (self.config.app_version,),
            parent = self.root)

    def cmd_rest(self, event=None):
        self.notify_observers('command:rest', None)

    def cmd_sync_current_note(self, event=None):
        self.notify_observers('command:sync_current_note', None)
        
    def cmd_sync_full(self, event=None):
        self.notify_observers('command:sync_full', None)
        
    def handler_housekeeper(self):
        # nvPY will do saving and syncing!
        self.notify_observers('keep:house', None)
        
        # check if titles need refreshing
        refresh_notes_list = False
        prev_title = None
        prev_modifydate = None
        prev_pinned = 0
        for i,o in enumerate(self.notes_list_model.list):
            # order should be the same as our listbox
            nt = utils.get_note_title(o.note)
            ot = self.notes_list.get_title(i)
            # if we strike a note with an out-of-date title, redo.
            if nt != ot:
                logging.debug('title "%s" resync' % (nt,))
                refresh_notes_list = True
                break

            # compare modifydate timestamp in our notes_list_model to what's displayed
            # if these are more than 60 seconds apart, we want to update our
            # mod-date display.
            md = float(o.note.get('modifydate', 0))
            omd = self.notes_list.get_modifydate(i)
            if abs(md - omd) > 60:
                # we log the title
                logging.debug('modifydate "%s" resync' % (nt,))
                refresh_notes_list = True
                break

            pinned = utils.note_pinned(o.note)
            old_pinned = self.notes_list.get_pinned(i)
            if pinned != old_pinned:
                # we log the title
                logging.debug('pinned "%s" resync' % (nt,))
                refresh_notes_list = True
                break

            tags = o.note.get('tags', 0)
            old_tags = self.notes_list.get_tags(i)
            if tags != old_tags:
                # we log the title
                logging.debug('tags "%s" resync' % (nt,))
                refresh_notes_list = True
                break

            if self.config.sort_mode == 0:
                # alpha
                if prev_title is not None and prev_title > nt:
                    logging.debug("alpha resort triggered")
                    refresh_notes_list = True
                    break
                
                prev_title = nt
                
            else:

                # we go from top to bottom, newest to oldest
                # this means that prev_modifydate (above) needs to be larger
                # than md (below). if it's not, re-sort.
                if prev_modifydate is not None and prev_modifydate < md and \
                   not prev_pinned:
                    logging.debug("modifydate resort triggered")
                    refresh_notes_list = True
                    break
                
                prev_modifydate = md
                if self.config.pinned_ontop:
                    prev_pinned = utils.note_pinned(o.note)
            
        if refresh_notes_list:
            self.refresh_notes_list()
        
        self.root.after(self.config.housekeeping_interval_ms, self.handler_housekeeper)
        
    def handler_pinned_checkbutton(self, *args):
        self.notify_observers('change:pinned',
            utils.KeyValueObject(value=self.pinned_checkbutton_var.get()))

    def handler_search_enter(self, evt):
        # user has pressed enter whilst searching
        # 1. if a note is selected, focus that
        # 2. if nothing is selected, create a new note with this title

        if self.notes_list.selected_idx >= 0:
            self.text_note.focus()
            self.text_note.see(tk.INSERT)
            
        else:
            # nothing selected
            self.notify_observers('create:note', utils.KeyValueObject(title=self.get_search_entry_text()))
            # the note will be created synchronously, so we can focus the text area already
            self.text_note.focus()
        
    def handler_search_entry(self, *args):
        self.notify_observers('change:entry',
                              utils.KeyValueObject(value=self.search_entry_var.get()))

    def handler_tags_entry(self, *args):
        self.notify_observers('change:tags',
            utils.KeyValueObject(value=self.tags_entry_var.get()))

    def handler_click_link(self, link):
        if link.startswith('[['):
            link = link[2:-2]
            self.notify_observers('click:notelink', link)

        else:
            webbrowser.open(link)
            
    def activate_search_string_highlights(self):
        t = self.text_note
        
        # remove all existing tags
        for tag in self.text_tags_search:
            t.tag_remove(tag, '1.0', 'end')
        
        del self.text_tags_search[:]
        
        st = self.get_search_entry_text()
        if not st:
            return
        
        # take care of invalid regular expressions...
        try:
            if self.config.case_sensitive == 0: 
                pat = re.compile(st, re.I)
            else:
                pat = re.compile(st)
        except re.error:
            return
        
        for mo in pat.finditer(t.get('1.0', 'end')):

            # start creating a new tkinter text tag
            tag = 'search-%d' % (len(self.text_tags_search),)
            t.tag_config(tag, background="yellow")

            # mo.start(), mo.end() or mo.span() in one go
            t.tag_add(tag, '1.0+%dc' % (mo.start(),), '1.0+%dc' %
                    (mo.end(),))

            # record the tag name so we can delete it later
            self.text_tags_search.append(tag)
            
        

    def activate_links(self):
        """
        Also see this post on URL detection regular expressions:
        http://www.regexguru.com/2008/11/detecting-urls-in-a-block-of-text/
        (mine is slightly modified)
        """


        t = self.text_note
        # the last group matches [[bla bla]] inter-note links
        pat = \
        r"\b((https?|ftp|file)://[-A-Za-z0-9+&@#/%?=~_|!:,.;]*[A-Za-z0-9+&@#/%=~_|])|(\[\[[^][]*\]\])"

        # remove all existing tags
        for tag in self.text_tags_links:
            t.tag_remove(tag, '1.0', 'end')

        del self.text_tags_links[:]
        
        for mo in re.finditer(pat,t.get('1.0', 'end')):
            # extract the link from the match object
            if mo.groups()[2] is not None:
                link = mo.groups()[2]
                ul = 0
            else:
                link = mo.groups()[0]
                ul = 1

            # start creating a new tkinter text tag
            tag = 'web-%d' % (len(self.text_tags_links),)
            t.tag_config(tag, foreground="blue", underline=ul)
            # hovering should give us the finger (cursor) hehe
            t.tag_bind(tag, '<Enter>', 
                    lambda e: t.config(cursor="hand2"))
            t.tag_bind(tag, '<Leave>', 
                    lambda e: t.config(cursor=""))
            # and clicking on it should do something sensible
            t.tag_bind(tag, '<Button-1>', lambda e, link=link:
                    self.handler_click_link(link))

            # mo.start(), mo.end() or mo.span() in one go
            t.tag_add(tag, '1.0+%dc' % (mo.start(),), '1.0+%dc' %
                    (mo.end(),))

            # record the tag name so we can delete it later
            self.text_tags_links.append(tag)


    def handler_text_change(self, evt):
        self.notify_observers('change:text', None)
        # FIXME: consider having this called from the housekeeping
        # handler, so that the poor regexp doesn't have to do every
        # single keystroke.
        self.activate_links()
        self.activate_search_string_highlights()

    def is_note_different(self, note):
        """
        Determine if note would cause a UI update.
        """

        if self.get_text() != note.get('content'):
            return True

        tags = note.get('tags', [])
        # get list of string tags from ui
        ui_tags = utils.sanitise_tags(self.tags_entry_var.get())
        if ui_tags != tags:
            return True

        if bool(self.pinned_checkbutton_var.get()) != bool(utils.note_pinned(note)):
            return True

    def observer_notes_list(self, notes_list_model, evt_type, evt):
        if evt_type == 'set:list':
            # re-render!
            self.set_notes(notes_list_model.list)
            
    def main_loop(self):
        self.root.mainloop()

    def mute_note_data_changes(self):
        self.mute('change:text')
        self.mute('change:tags')
        self.mute('change:pinned')
        
    def set_status_text(self, txt):
        self.statusbar.set_status(txt)
        
    def set_note_data(self, note, reset_undo=True, content_unchanged=False):
        """Replace text in editor with content.
        
        This is usually called when a new note is selected (case 1), or
        when a modified note comes back from the server (case 2).
        
        @param reset_undo: Set to False if you don't want to have the undo
        buffer to reset.
        @param content_unchanged: Set to True if you know that the content
        has not changed, only the tags and pinned status.
        """

        if not content_unchanged:
            self.text_note.delete(1.0, tk.END) # clear all

        if note is not None:
            if not content_unchanged:
                self.text_note.insert(tk.END, note['content'])

            # default to an empty array for tags
            tags=note.get('tags', [])
            self.tags_entry_var.set(','.join(tags))
            self.pinned_checkbutton_var.set(utils.note_pinned(note))

        if reset_undo:
            # usually when a new note is selected, we want to reset the
            # undo buffer, so that a user can't undo right into the previously
            # selected note.
            self.text_note.edit_reset()
        
        
    def set_notes(self, notes):
        # clear the notes list
        self.notes_list.clear()
        taglist = []
        
        for o in notes:
            tags = o.note.get('tags')
            if tags:
                taglist += tags
            self.notes_list.append(o.note, utils.KeyValueObject(tagfound=o.tagfound))

        taglist = list(set(self.taglist + taglist))
        if len(taglist) > len(self.taglist):
            self.taglist=taglist
            self.search_entry.set_completion_list(self.taglist)

    def show_error(self, title, msg):
        tkMessageBox.showerror(title, msg)

    def show_info(self, title, msg):        
        tkMessageBox.showinfo(title, msg,parent = self.root)

    def show_warning(self, title, msg):
        tkMessageBox.showwarning(title, msg)

    def unmute_note_data_changes(self):
        self.unmute('change:text')
        self.unmute('change:tags')
        self.unmute('change:pinned')


    def update_selected_note_data(self, note):
        """
        Update currently selected note's data.

        This is called when the user triggers a per-note sync and a newer
        note comes back, but also when the search string changes, and the
        currently selected note gets a newer version due to background or
        foreground syncing.

        We take care only to update the note content if it has actually
        changed, to minimise visual glitches.
        """

        # the user is not changing anything, so we don't want the event to fire
        self.mute_note_data_changes()

        current_content = self.get_text()
        new_content = note.get('content', '')

        if new_content != current_content:
            # store cursor position
            cursor_pos = self.text_note.index(tk.INSERT)
            # also store visible window
            first, last = self.text_note.yview()

            # set new note contents, pinned status and tags
            # but keep user's undo buffer
            self.set_note_data(note, reset_undo=False)

            # restore visible window
            self.text_note.yview('moveto', first)
            self.text_note.mark_set(tk.INSERT, cursor_pos)
            self.activate_links()
            self.activate_search_string_highlights()

        else:
            # we know the content is the same, so we only set the rest
            # obviously keep user's undo buffer.
            self.set_note_data(note, reset_undo=False, content_unchanged=True)

        # reactivate event handlers
        self.unmute_note_data_changes()


    def word_count(self):
        """
        Display count of total words and selected words in a dialog box.
        """

        sel = self.get_selected_text()
        slen = len(sel.split())

        txt = self.get_text()
        tlen = len(txt.split())

        self.show_info('Word Count', '%d words in total\n%d words in selection' % (tlen,slen))
