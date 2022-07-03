# nvPY: cross-platform note-taking app with simplenote syncing
# copyright 2012 by Charl P. Botha <cpbotha@vxlabs.com>
# new BSD license

import logging
import os
import re
from . import search_entry
from . import tk
from tkinter import messagebox as tkMessageBox
import tkinter.font as tkFont  # type:ignore
from . import utils
import threading
from . import events
import typing
import subprocess
import platform


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
        return "WidgetRedirector(%s<%s>)" % (self.widget.__class__.__name__, self.widget._w)

    def close(self):
        for name in self.dict:
            self.unregister(name)

        widget = self.widget
        del self.widget
        orig = self.orig
        del self.orig
        tk = widget.tk
        w = widget._w
        tk.deletecommand(w)
        tk.call("rename", orig, w)

    def register(self, name, function):
        if name in self.dict:
            previous = self.dict[name]

        else:
            previous = OriginalCommand(self, name)

        self.dict[name] = function
        setattr(self.widget, name, function)
        return previous

    def unregister(self, name):
        if name in self.dict:
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
    def __init__(self, master=None, cnf=None, **kw):
        tk.Text.__init__(self, master, cnf or {}, **kw)

        # now attach the redirector
        self.redir = WidgetRedirector(self)
        self.orig_insert = self.redir.register("insert", self.new_insert)
        self.orig_delete = self.redir.register("delete", self.new_delete)
        self.fonts = [kw['font']]

    def new_insert(self, *args):
        self.orig_insert(*args)
        self.event_generate('<<Change>>')

    def new_delete(self, *args):
        self.orig_delete(*args)
        self.event_generate('<<Change>>')


class HelpBindings(tk.Toplevel):
    def __init__(self, parent=None):
        tk.Toplevel.__init__(self, parent)
        self.title("Help | Bindings")

        from . import bindings

        msg = tk.Text(self, width=80, wrap=tk.NONE)
        msg.insert(tk.END, bindings.description)
        msg.config(state=tk.DISABLED)
        msg.pack()

        button = tk.Button(self, text="Dismiss", command=self.destroy)
        button.pack()


class SuggestionEntry(tk.Entry):
    """
    SuggestionEntry shows suggestion tag list, and user can be complete the tag.

    How to use:
        Up arrow key:    select the previous tag in suggestion tag list.
        Down arrow key:  select the next tag in suggestion tag list.
        Types a word:    narrow down the suggestion tag list.
        Right arrow key and Return key:  enter the currently selected tag.

    args:
        completion_func(searchWord) - returns a list of matching tags.
    """
    def __init__(self, completion_func, *args, **kwargs):
        if "textvariable" in kwargs:
            self.var = kwargs["textvariable"]
        else:
            self.var = tk.StringVar()
            kwargs = kwargs.copy()
            kwargs["textvariable"] = self.var

        self.completion_func = completion_func
        self.listbox = None
        self.listbox_height = 6  # lines
        self.listbox_lines = 0
        tk.Entry.__init__(self, *args, **kwargs)

        # apply a monkey patch.
        self.orig_bind, self.bind = self.bind, self.new_bind

        self.var.trace('w', self.changed)
        self.orig_bind("<Right>", self.selection)
        self.orig_bind("<Return>", self.selection)
        self.orig_bind("<Up>", self.moveUp)
        self.orig_bind("<Down>", self.moveDown)
        self.orig_bind("<Control-space>", self.showSuggestions)
        self.orig_bind("<FocusIn>", self.showSuggestions)
        self.orig_bind("<FocusOut>", self.hideSuggestions)

    def new_bind(self, sequence=None, func=None, add=None):
        """
        Hijack key bindings
        """
        orig_func = func
        if sequence == '<Return>' and func is not None:

            def handle_return(*args):
                if self.listbox is not None:
                    # If completion word list is shown, call to self.selection() instead of func().
                    self.selection()
                    return
                return orig_func(*args)

            func = handle_return
        elif sequence == '<Escape>' and func is not None:

            def handle_escape(*args):
                if self.listbox is not None:
                    # If completion word list is shown, close it.
                    self._destroy_listbox()
                    return
                return orig_func(*args)

            func = handle_escape
        return self.orig_bind(sequence, func, add)

    def _create_listbox(self):
        self.listbox = tk.Listbox(width=self["width"], height=self.listbox_height)
        self.listbox.bind("<Button-1>", self.selection)
        self.listbox.bind("<Right>", self.selection)
        self.listbox.place(
            in_=self.master,
            relx=0.0,
            rely=0.0,
            x=self.winfo_x(),
            y=self.winfo_y() - self.listbox.winfo_reqheight(),
        )

    def _update_listbox(self):
        if self.listbox is None:
            return

        selectedWord = self.listbox.get(tk.ACTIVE)
        words = tuple(self.completion_func(self.var.get()))
        self.listbox_lines = len(words)
        self.listbox.delete(0, tk.END)
        for w in words:
            self.listbox.insert(tk.END, w)

        self.listbox.place(
            in_=self.master,
            relx=0.0,
            rely=0.0,
            x=self.winfo_x(),
            y=self.winfo_y() - self.listbox.winfo_reqheight(),
        )

        try:
            index = words.index(selectedWord)
        except ValueError:
            index = '0'
        self._select_listbox(index)

    def _select_listbox(self, index):
        for old_index in self.listbox.curselection():
            self.listbox.selection_clear(first=old_index)

        if int(index) < 0:
            index = '0'
        elif self.listbox_lines <= int(index):
            index = str(self.listbox_lines - 1)

        self.listbox.selection_set(first=index)
        self.listbox.see(index)
        self.listbox.activate(index)

    def _destroy_listbox(self):
        if self.listbox is None:
            return

        self.listbox.destroy()
        self.listbox = None

    def changed(self, *args):
        self._update_listbox()

    def selection(self, *args):
        if self.listbox is None:
            return

        selected_tag = self.listbox.get(tk.ACTIVE)
        if selected_tag:
            self.var.set(selected_tag)
        self._destroy_listbox()
        self.icursor(tk.END)

    def moveUp(self, *args):
        if self.listbox is None:
            self._create_listbox()
            self._update_listbox()

        if len(self.listbox.curselection()) == 0:
            index = '0'
        else:
            oldIndex = self.listbox.curselection()[0]
            index = str(int(oldIndex) - 1)
        self._select_listbox(index)

    def moveDown(self, *args):
        if self.listbox is None:
            self._create_listbox()
            self._update_listbox()

        if len(self.listbox.curselection()) == 0:
            index = '0'
        else:
            oldIndex = self.listbox.curselection()[0]
            index = str(int(oldIndex) + 1)
        self._select_listbox(index)

    def showSuggestions(self, *args):
        if self.listbox is not None:
            # The suggestion list is already displayed.
            return
        self._create_listbox()
        self._update_listbox()

    def hideSuggestions(self, *args):
        if self.listbox is None:
            # The suggestion list is already hidden.
            return
        self._destroy_listbox()


class TagList(tk.Toplevel):
    # search tag callback
    def tagsel(self, box, view):
        sel = box.curselection()
        if len(sel) != 1: return
        for idx in sel:
            item = box.get(idx)
            view.set_search_entry_text("t:%s" % item)
        self.destroy()

    def __init__(self, parent, taglist, view):
        tk.Toplevel.__init__(self, parent)
        self.title("List all tags")
        self.bind("<Escape>", lambda a: self.destroy())

        box = tk.Listbox(self, width=30, selectmode=tk.BROWSE)
        if taglist:
            alltags = list(set(taglist))
            alltags.sort(key=lambda x: x.upper())
            for item in alltags:
                box.insert(tk.END, item)
            # bind double click and Enter (on box)
            box.bind("<Double-Button-1>", lambda a: self.tagsel(box, view))
            box.bind("<Return>", lambda a: self.tagsel(box, view))
            box.focus()
        else:
            box.insert(tk.END, "No tags defined")

        box.pack()

        button = tk.Button(self, text="Dismiss", command=self.destroy)
        button.pack()
        x = parent.winfo_x() + 100
        y = parent.winfo_y() + 100

        self.geometry("+%d+%d" % (x, y))  # Put me over root window


#########################################################################
class StatusBar(tk.Frame):
    """Adapted from the tkinterbook.
    """

    # actions
    # global status
    # note status

    # http://colorbrewer2.org#type=sequential&scheme=OrRd&n=3
    # from light to dark orange; colorblind-safe scheme
    #NOTE_STATUS_COLORS = ["#FEE8C8", "#FDBB84", "#E34A33"]

    # http://colorbrewer2.org#type=diverging&scheme=RdYlBu&n=5
    # diverging red to blue; colorblind-safe scheme
    # red, lighter red, light yellow, light blue, dark blue
    NOTE_STATUS_COLORS = ["#D7191C", "#FDAE61", "#FFFFBF", "#ABD9E9", "#2C7BB6"]
    # 0 - saved and synced - light blue - 3
    # 1 - saved - light yellow - 2
    # 2 - modified - lighter red - 1
    # 3 - full syncing - lighter red - 1
    NOTE_STATUS_LUT = {0: 3, 1: 2, 2: 1, 3: 1}

    def __init__(self, master):
        tk.Frame.__init__(self, master)

        self.status = tk.Label(self, relief=tk.SUNKEN, anchor=tk.W, width=40)
        self.status.pack(side=tk.LEFT, fill=tk.X, expand=1)

        self.centre_status = tk.Label(self, relief=tk.SUNKEN, anchor=tk.W, width=35)
        self.centre_status.pack(side=tk.LEFT, fill=tk.X, padx=5)

        self.note_status = tk.Label(self, relief=tk.SUNKEN, anchor=tk.W, width=25)
        self.note_status.pack(side=tk.LEFT, fill=tk.X)

    def set_centre_status(self, fmt, *args):
        self.centre_status.config(text=fmt % args)
        self.centre_status.update_idletasks()

    def set_note_status(self, fmt, *args):
        """ *.. .s. .sS
        """
        self.note_status.config(text=fmt % args)
        self.note_status.update_idletasks()

    def set_note_status_color(self, status_idx):
        """
        @param status_idx: 0 - saved and synced; 1 - saved; 2 - modified
        """

        color_idx = self.NOTE_STATUS_LUT[status_idx]
        self.note_status.config(background=self.NOTE_STATUS_COLORS[color_idx])

    def set_status(self, fmt, *args):
        self.status.config(text=fmt % args)
        self.status.update_idletasks()

    def clear_status(self):
        self.status.config(text="")
        self.status.update_idletasks()


class NotesListConfig(typing.NamedTuple):
    colors: typing.Any  # This type should ColorConfig, but specify any to solve circular import error.
    layout: str
    print_columns: int
    hide_time: int
    hide_tags: int


class NoteConfig(typing.NamedTuple):
    tagfound: int


class NotesList(tk.Frame):
    """
    @ivar note_headers: list containing tuples with each note's title, tags,
    modified date and so forth. Always in sync with what is displayed.
    """

    TITLE_COL = 0
    TAGS_COL = 1
    MODIFYDATE_COL = 2
    PINNED_COL = 3
    CREATEDATE_COL = 4

    def __init__(self, master, font_family, font_size, config: NotesListConfig):
        tk.Frame.__init__(self, master)

        yscrollbar = tk.Scrollbar(self)
        yscrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        f = tkFont.Font(family=font_family, size=font_size)

        # tkFont.families(root) returns list of available font family names
        # this determines the width of the complete interface (yes)
        # size=-self.config.font_size
        self.text = tk.Text(self,
                            height=25,
                            wrap=tk.NONE,
                            font=f,
                            yscrollcommand=yscrollbar.set,
                            undo=False,
                            foreground=config.colors.text,
                            background=config.colors.background)
        # change default font at runtime with:
        #text.config(font=f)

        self.text.config(cursor="arrow")
        self.disable_text()
        self.text.pack(fill=tk.BOTH, expand=1)

        # tags for all kinds of styling ############################
        ############################################################

        self.text.tag_config("selected", background=config.colors.selected_note)

        self.text.tag_config("pinned", foreground=config.colors.note_info)

        # next two lines from:
        # http://stackoverflow.com/a/9901862/532513
        bold_font = tkFont.Font(self.text, self.text.cget("font"))
        bold_font.configure(weight="bold")
        self.text.tag_config("title", font=bold_font)

        italic_font = tkFont.Font(self.text, self.text.cget("font"))
        italic_font.configure(slant="italic")
        self.text.tag_config("tags", font=italic_font, foreground=config.colors.note_info)
        self.text.tag_config("found",
                             font=italic_font,
                             foreground=config.colors.note_info,
                             background=config.colors.highlight_note_info)

        self.text.tag_config("modifydate", foreground=config.colors.note_info)

        yscrollbar.config(command=self.text.yview)

        self._bind_events()

        self.selected_idx = -1
        # list containing tuples with each note's title, tags,
        self.note_headers: typing.List[tuple] = []

        self.layout = config.layout
        self.hide_time = config.hide_time
        self.hide_tags = config.hide_tags
        self.print_columns = config.print_columns
        if bold_font.measure(' ') > f.measure(' '):
            self.cwidth = bold_font.measure(' ')
        else:
            self.cwidth = f.measure(' ')
        self.fonts = [f, italic_font, bold_font]

    def append(self, note, config):
        """
        @param note: The complete note dictionary.
        """

        title = utils.get_note_title(note)
        tags = note.get('tags')
        modifydate = float(note.get('modifydate'))
        pinned = utils.note_pinned(note)
        createdate = float(note.get('createdate'))
        self.note_headers.append((title, tags, modifydate, pinned, createdate))

        self.enable_text()

        if self.layout == "vertical" and self.print_columns == 1:
            nrchars, rem = divmod(self.text.winfo_width(), self.cwidth)
            if self.hide_time:
                nrchars = int(nrchars)
            else:
                nrchars = int(nrchars) - 8

            if self.hide_tags:
                cellwidth = int(nrchars)
            else:
                cellwidth = int(nrchars) / 2

            if pinned:
                title += ' *'

            self.text.insert(tk.END, u'{0:<{w}}'.format(title[:cellwidth - 1], w=cellwidth), ("title,"))

            if tags and not self.hide_tags:
                if config.tagfound:
                    self.text.insert(tk.END, u'{0:<{w}}'.format(','.join(tags)[:cellwidth - 1], w=cellwidth),
                                     ("found", ))
                else:
                    self.text.insert(tk.END, u'{0:<{w}}'.format(','.join(tags)[:cellwidth - 1], w=cellwidth),
                                     ("tags", ))

            if not self.hide_time:
                self.text.insert(tk.END, ' ' + utils.human_date(createdate), ("createdate", ))

            # tags can be None (newly created note) or [] or ['tag1', 'tag2']
        else:
            self.text.insert(tk.END, title, ("title,"))

            if pinned:
                self.text.insert(tk.END, ' *', ("pinned", ))

            # latest modified first is the default mode
            # we could consider showing createddate here IF the sort mode
            # is configured to be latest created first
            if not self.hide_time:
                self.text.insert(tk.END, ' ' + utils.human_date(modifydate), ("modifydate", ))

            # tags can be None (newly created note) or [] or ['tag1', 'tag2']
            if tags and not self.hide_tags:
                if config.tagfound:
                    self.text.insert(tk.END, ' ' + ','.join(tags), ("found", ))
                else:
                    self.text.insert(tk.END, ' ' + ','.join(tags), ("tags", ))

        self.text.insert(tk.END, '\n')

        self.disable_text()

    def _bind_events(self):
        # Text widget events ##########################################

        self.text.bind("<Button 1>", self.cmd_text_button1)
        self.text.bind("<Control-c>", self.cmd_text_copy)

        # same deal as for pageup
        # we have to stop the text widget class event handler from firing
        def cmd_up(e):
            self.select_prev(silent=False)
            return "break"

        self.text.bind("<Up>", cmd_up)
        self.text.bind("<Control-k>", cmd_up)

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
        self.text.bind("<Control-j>", cmd_down)

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

    def cmd_text_copy(self, event):
        if self.selected_idx >= 0:
            self.text.clipboard_clear()
            self.text.clipboard_append(self.get_title(self.selected_idx))
        return "break"

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

    def get_createdate(self, idx):
        """
        Return createdate of idx'th note.

        @returns: createdate as a floating point timestamp.
        """
        return self.note_headers[idx][NotesList.CREATEDATE_COL]

    def idx_to_index_range(self, idx):
        """
        Given a note index idx, return the Tkinter text index range for
        the start and end of that note.
        """

        # tkinter text first line is 1, but first column is 0
        row = idx + 1
        start = "%d.0" % (row, )
        end = "%d.end" % (row, )

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


tkinter_umlauts = ['odiaeresis', 'adiaeresis', 'udiaeresis', 'Odiaeresis', 'Adiaeresis', 'Udiaeresis', 'ssharp']


class TriggeredcompleteEntry(tk.Entry):
    """
    Subclass of tk.Entry that features triggeredcompletion.

    How this works: User types first part of tag, then triggers complete with
    ctrl-space. The first matching tag is shown. The user can either continue
    pressing ctrl-space to see more matching tags, or right arrow to select
    the current suggestion and continue typing. Backspace will delete the
    suggested part.

    To enable triggeredcompletion use set_completion_list(list) to define
    a list of possible strings to hit.
    To cycle through hits use CTRL <space> keys.

    @ivar cycle: if 1, then we're cycling through alternative completions.
    """
    def __init__(self, master, case_sensitive, **kw):
        tk.Entry.__init__(self, master, **kw)
        self.case_sensitive = case_sensitive
        # make sure we're initialised, else the event handler could generate
        # exceptions checking for instance variables that don't exist yet.
        self.set_completion_list([])
        self.bind('<KeyRelease>', self.handle_keyrelease)

    def set_completion_list(self, completion_list):
        self._completion_list = completion_list
        self._hits = []
        self._hit_index = 0
        self.wstart = 0
        self.position = 0
        self.cycle = 0

    def triggeredcomplete(self):
        """triggeredcomplete the Entry, delta may be 0/1 to cycle through possible hits"""

        if self.cycle:  # need to delete selection otherwise we would fix the current position
            self.delete(self.position, tk.END)
            self._hit_index += 1
            if self._hit_index == len(self._hits):
                self._hit_index = 0

        else:  # set position to end so selection starts where textentry ended
            self.position = len(self.get())
            wstartsc = self.get().rfind(':')
            wstartsp = self.get().rfind(' ')
            if wstartsc < 0 and wstartsp < 0:
                self.wstart = 0
            elif wstartsc > wstartsp:
                self.wstart = wstartsc + 1
            else:
                self.wstart = wstartsp + 1

            # collect hits
            _hits = []
            for element in self._completion_list:
                if self.case_sensitive == 0:
                    if element.lower().startswith(self.get()[self.wstart:].lower()):
                        _hits.append(element)
                else:
                    if element.startswith(self.get()[self.wstart:]):
                        _hits.append(element)

            self._hit_index = 0
            self._hits = _hits

        # now finally perform the triggered completion
        if self._hits:
            self.delete(self.wstart, tk.END)
            self.insert(self.wstart, self._hits[self._hit_index])
            self.select_range(self.position, tk.END)

    def handle_keyrelease(self, event):
        """event handler for the keyrelease event on this widget"""
        ctrl = ((event.state & 0x0004) != 0)

        # special case handling below only if we are in cycle mode.
        if self.cycle:
            if event.keysym == "BackSpace":
                self.cycle = 0
                self.delete(self.index(tk.INSERT), tk.END)
                self.position = self.index(tk.END)

            if event.keysym == "Right":
                self.position = self.index(tk.END)  # go to end (no selection)
                self.cycle = 0

            if event.keysym == "Left":
                self.cycle = 0

        if event.keysym == "space" and ctrl:
            # cycle
            self.triggeredcomplete()
            if self.cycle == 0:
                self.cycle = 1


class TriggeredcompleteText(RedirectedText):
    """
    TriggeredcompleteText completes the note title when I press "[[".
    This class behaves like the TriggeredcompleteEntry.
    """
    def __init__(self, master, case_sensitive, **kwargs):
        RedirectedText.__init__(self, master, **kwargs)
        self.case_sensitive = case_sensitive
        # make sure we're initialised, else the event handler could generate
        # exceptions checking for instance variables that don't exist yet.
        self.set_completion_list([])
        self.bind('<KeyRelease>', self.handle_keyrelease)

        self.old_cursor_pos = 0
        self.old_content = ""

    def set_completion_list(self, completion_list):
        self._completion_list = completion_list
        self._hits = []
        self._hit_index = 0
        self.cycle = 0
        self.comp_word_start = None
        self.comp_word_end = None

    def triggeredcomplete(self):
        """triggeredcomplete the Entry, delta may be 0/1 to cycle through possible hits"""
        try:
            first_index = "1.0"
            current_line = self.get(first_index, tk.INSERT).splitlines()[-1]
            current_line += self.get(tk.INSERT, tk.END).splitlines()[0]
            line, cur_col = self.index(tk.INSERT).split(".")
            cur_col = int(cur_col)

            word_start = current_line.rindex("[[", 0, int(cur_col)) + 2
            try:
                word_end = current_line.index("]]", word_start) + 2
                word_prefix_end = word_end
                if word_end < cur_col:
                    # cursor position is outside the link string like "[[...]]".
                    return
                elif word_end - 2 < cur_col:
                    # cursor position is upon "]]".
                    word_prefix_end = word_end - 2

                if self.cycle:
                    word_prefix_end = int(self.cursor_index.split(".")[1])
            except ValueError:
                # "]]" is not found. word_end overwrites the cursor position.
                word_prefix_end = cur_col
                word_end = cur_col

            bow_index = "%s.%s" % (line, str(word_start))  # index of beginning of word
            eowp_index = "%s.%s" % (line, str(word_prefix_end))  # index of ending of word_prefix
            eow_index = "%s.%s" % (line, str(word_end))  # index of ending of word

            word_prefix = current_line[word_start:word_prefix_end].rstrip("]]")
            word = current_line[word_start:word_end].rstrip("]]")
        except IndexError:
            # when press "ctrl+space" key on empty note, will be occur IndexError.
            return
        except ValueError:
            # when press "ctrl+space" key on a line not including of "[[", str.index() will be occur ValueError.
            return

        if self.cycle:
            self._hit_index += 1
            if self._hit_index == len(self._hits):
                self._hit_index = 0

        else:  # set position to end so selection starts where textentry ended
            self.cursor_index = eowp_index
            self.comp_word_start = bow_index
            self.comp_word_end = eow_index

            # collect hits
            hits = []
            for element in self._completion_list:
                if self.case_sensitive == 0:
                    if element.lower().startswith(word_prefix.lower()):
                        hits.append(element)
                else:
                    if element.startswith(word_prefix):
                        hits.append(element)

            self._hit_index = 0
            self._hits = hits

        # now finally perform the triggered completion
        if self._hits:
            new_word = self._hits[self._hit_index] + "]]"
            new_eow_index = "%s.%s" % (line, word_start + len(new_word))  # index of ending of word

            self.delete(self.comp_word_start, self.comp_word_end)
            self.insert(bow_index, new_word)
            self.tag_add("sel", self.cursor_index, new_eow_index)

            self.comp_word_start = bow_index
            self.comp_word_end = new_eow_index

    def handle_keyrelease(self, event):
        """event handler for the keyrelease event on this widget"""
        ctrl = ((event.state & 0x0004) != 0)

        # special case handling below only if we are in cycle mode.
        if self.cycle:
            if event.keysym == "BackSpace":
                self.cycle = 0
                return

            if event.keysym in ("Right", "Return"):
                self.cycle = 0
                if event.keysym == "Return":
                    # restore content
                    self.delete("1.0", tk.END)
                    self.insert("1.0", self.old_content)
                # restore cursor position
                self.mark_set("insert", self.old_cursor_pos)
                return

        if event.keysym == "space" and ctrl:
            # cycle
            self.triggeredcomplete()
            if self.cycle == 0:
                self.cycle = 1
            self.old_cursor_pos = self.index(tk.INSERT)
            self.old_content = self.get("1.0", tk.END)
            return

        cursor_pos = self.index(tk.INSERT)
        content = self.get("1.0", tk.END)
        if self.old_cursor_pos == cursor_pos and self.old_content == content:
            # ignore
            return
        self.old_cursor_pos = cursor_pos
        self.old_content = content
        # other keys pressed
        self.cycle = 0


class View(utils.SubjectMixin):
    """Main user interface class.
    """
    def __init__(self, config, notes_list_model, sort_modes: typing.Tuple[str, ...] = ('random', )):
        utils.SubjectMixin.__init__(self)

        self.config = config
        self.taglist = None
        self.sort_modes = sort_modes

        notes_list_model.add_observer('set:list', self.observer_notes_list)
        self.notes_list_model = notes_list_model
        self.timer_ids_lock = threading.Lock()
        self.timer_ids: typing.Set[typing.Any] = set()

        tk.Tk.report_callback_exception = self.handle_unexpected_error
        self._create_ui()
        self._bind_events()

        # set default font for dialog boxes on Linux
        # on Windows, tkinter uses system dialogs in any case
        self.root.option_add('*Dialog.msg.font', 'Helvetica 12')

        self.text_tags_links: typing.List[str] = []
        self.text_tags_search: typing.List[str] = []

        self.search_entry.focus_set()

    def handle_unexpected_error(self, *args):
        # An unexpected error has occurred. The program MUST be stop immediately.
        self.cancel_timers()

        err = args[1]
        if isinstance(err, tk.Ucs4NotSupportedError):
            title, msg = 'UCS-4 not supported', str(err)
        else:
            import traceback
            stackTrace = ''.join(traceback.format_exception(*args))
            title, msg = "Unexpected Error", stackTrace

        logging.error(msg)
        self.show_error(title, msg)
        exit(1)

    def askyesno(self, title, msg):
        return tkMessageBox.askyesno(title, msg)

    def cmd_notes_list_select(self, evt=None):
        sidx = self.notes_list.selected_idx
        self.notify_observers('select:note', events.NoteSelectionChangedEvent(sel=sidx))

    def cmd_root_delete(self, evt=None):
        is_delete = False
        if self.config.confirm_delete:
            # double-check that the user really means delete
            # https://github.com/cpbotha/nvpy/issues/119
            if tkMessageBox.askyesno("Really delete note?",
                                     "Are you sure you want to delete the current note?",
                                     default=tkMessageBox.NO):
                is_delete = True
        else:
            # delete a note without confirmation.
            is_delete = True

        if is_delete:
            sidx = self.notes_list.selected_idx
            self.notify_observers('delete:note', events.NoteSelectionChangedEvent(sel=sidx))

    def cmd_root_new(self, evt=None):
        # this'll get caught by a controller event handler
        self.notify_observers('create:note', events.NoteCreatedEvent(title=self.get_search_entry_text()))
        # the note will be created synchronously, so we can focus the text area already
        self.text_note.focus()

    def cmd_select_all(self, evt=None):
        self.text_note.tag_add("sel", "1.0", "end-1c")
        # we don't want the text bind_class() handler for Ctrl-A to be fired.
        return "break"

    def set_note_editing(self, enable=True):
        """Enable or disable note editing controls.

        This is used to disable the controls when no note has been selected.
        Disables note text widget, tag entry and pinned checkbutton.

        @param enable: enable controls if True, else disable.
        @return: Nothing.
        """

        state = tk.NORMAL if enable else tk.DISABLED
        self.text_note.config(state=state)
        self.tags_entry.config(state=state)
        self.pinned_checkbutton.config(state=state)

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

        if status.full_syncing:
            s = 'Full syncing'
            self.statusbar.set_note_status_color(3)
            self.statusbar.set_note_status(s)
            return
        if status.modified:
            s = 'modified'
            self.statusbar.set_note_status_color(2)
        elif status.saved and status.synced:
            s = 'saved + synced'
            self.statusbar.set_note_status_color(0)
        elif status.saved:
            s = 'saved'
            self.statusbar.set_note_status_color(1)
        else:
            s = 'synced'
            self.statusbar.set_note_status_color(0)

        self.statusbar.set_note_status('Current note %s' % (s, ))

    def set_note_tally(self, filtered_notes, active_notes, total_notes):
        self.statusbar.set_centre_status('Listing %d / %d active notes (%d total)' %
                                         (filtered_notes, active_notes, total_notes))

    def set_search_entry_text(self, text):
        self.search_entry_var.set(text)

    def _bind_events(self):
        # make sure window close also goes through our handler
        self.root.protocol('WM_DELETE_WINDOW', self.handler_close)

        self.root.bind_all("<Control-g>", lambda e: self.tags_entry.focus())
        self.root.bind_all("<Control-question>", lambda e: self.cmd_help_bindings())
        self.root.bind_all("<Control-plus>", lambda e: self.cmd_font_size(+1))
        self.root.bind_all("<Control-minus>", lambda e: self.cmd_font_size(-1))
        self.root.bind_all("<Control-S>", lambda e: self.toggle_pinned_checkbutton())

        self.notes_list.bind("<<NotesListSelect>>", self.cmd_notes_list_select)
        # same behaviour as when the user presses enter on search entry:
        # if something is selected, focus the text area
        # if nothing is selected, try to create new note with
        # search entry value as name
        self.notes_list.text.bind("<Return>", self.handler_search_enter)
        self.notes_list.text.bind("<Escape>", lambda e: self.search_entry.focus())
        self.notes_list.text.bind("<Control-bracketleft>", lambda e: self.search_entry.focus())

        self.search_entry.bind("<Escape>", self.handler_search_escape)
        self.search_entry.bind("<Control-bracketleft>", self.handler_search_escape)
        # this will either focus current content, or
        # if there's no selection, create a new note.
        self.search_entry.bind("<Return>", self.handler_search_enter)

        self.search_entry.bind("<Up>", lambda e: self.notes_list.select_prev(silent=False))
        self.search_entry.bind("<Control-k>", lambda e: self.notes_list.select_prev(silent=False))
        self.search_entry.bind("<Prior>", lambda e: self.notes_list.select_prev(silent=False, delta=10))

        self.search_entry.bind("<Down>", lambda e: self.notes_list.select_next(silent=False))
        self.search_entry.bind("<Control-j>", lambda e: self.notes_list.select_next(silent=False))
        self.search_entry.bind("<Next>", lambda e: self.notes_list.select_next(silent=False, delta=10))

        self.text_note.bind("<<Change>>", self.handler_text_change)

        # user presses escape in text area, they go back to search box
        self.text_note.bind("<Escape>", lambda e: self.search_entry.focus())
        self.text_note.bind("<Control-bracketleft>", lambda e: self.search_entry.focus())
        # <Key>

        self.text_note.bind("<Control-BackSpace>", self.handler_control_backspace)
        self.text_note.bind("<Control-Delete>", self.handler_control_delete)
        self.text_note.bind("<Control-a>", self.cmd_select_all)
        self.text_note.bind("<Control-c>", self.handler_text_copy)

        self.tags_entry.bind("<Return>", self.handler_add_tags_to_selected_note)
        self.tags_entry.bind("<Escape>", lambda e: self.text_note.focus())

        self.search_entry_var.trace('w', self.handler_search_entry)
        self.cs_checkbutton_var.trace('w', self.handler_cs_checkbutton)
        self.search_mode_var.trace('w', self.handler_search_mode)
        self.pinned_checkbutton_var.trace('w', self.handler_pinned_checkbutton)
        self.sort_mode_var.trace('w', self.handler_sort_mode_change)
        self.pinned_on_top_var.trace('w', self.handler_pinned_on_top_change)

        self.after(self.config.housekeeping_interval_ms, self.handler_housekeeper)

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
        file_menu.add_command(label="New note", underline=0, command=self.cmd_root_new, accelerator="Ctrl+N")
        self.root.bind_all("<Control-n>", self.cmd_root_new)

        file_menu.add_command(label="Delete note", underline=0, command=self.cmd_root_delete, accelerator="Ctrl+D")
        self.root.bind_all("<Control-d>", self.cmd_root_delete)

        file_menu.add_separator()

        file_menu.add_command(label="Sync full", underline=5, command=self.cmd_sync_full)
        file_menu.add_command(label="Sync current note",
                              underline=0,
                              command=self.cmd_sync_current_note,
                              accelerator="Ctrl+S")
        self.root.bind_all("<Control-s>", self.cmd_sync_current_note)

        file_menu.add_separator()

        file_menu.add_command(label="Render Markdown to HTML",
                              underline=7,
                              command=self.cmd_markdown,
                              accelerator="Ctrl+M")
        self.root.bind_all("<Control-m>", self.cmd_markdown)

        self.continuous_rendering = tk.BooleanVar()
        self.continuous_rendering.set(False)
        file_menu.add_checkbutton(label="Continuous Markdown to HTML rendering",
                                  onvalue=True,
                                  offvalue=False,
                                  variable=self.continuous_rendering)

        file_menu.add_command(label="Render reST to HTML", underline=7, command=self.cmd_rest, accelerator="Ctrl+R")
        self.root.bind_all("<Control-r>", self.cmd_rest)

        file_menu.add_separator()

        file_menu.add_command(label="Exit", underline=1, command=self.handler_close, accelerator="Ctrl+Q")
        self.root.bind_all("<Control-q>", self.handler_close)

        # EDIT ##########################################################
        edit_menu = tk.Menu(menu, tearoff=False)
        menu.add_cascade(label="Edit", underline=0, menu=edit_menu)

        edit_menu.add_command(label="Undo",
                              accelerator="Ctrl+Z",
                              underline=0,
                              command=lambda: self.text_note.edit_undo())
        self.root.bind_all("<Control-z>", lambda e: self.text_note.edit_undo())

        edit_menu.add_command(label="Redo",
                              accelerator="Ctrl+Y",
                              underline=0,
                              command=lambda: self.text_note.edit_redo())
        self.root.bind_all("<Control-y>", lambda e: self.text_note.edit_redo())

        edit_menu.add_separator()

        edit_menu.add_command(label="Cut", accelerator="Ctrl+X", underline=2, command=self.cmd_cut)
        edit_menu.add_command(label="Copy", accelerator="Ctrl+C", underline=0, command=self.cmd_copy)
        edit_menu.add_command(label="Paste", accelerator="Ctrl+V", underline=0, command=self.cmd_paste)

        edit_menu.add_command(label="Select All", accelerator="Ctrl+A", underline=7, command=self.cmd_select_all)
        # FIXME: ctrl-a is usually bound to start-of-line. What's a
        # better binding for select all then?

        edit_menu.add_separator()

        edit_menu.add_command(label="Find",
                              accelerator="Ctrl+F",
                              underline=0,
                              command=lambda: self.search_entry.focus())
        self.root.bind_all("<Control-f>", self.search)

        # NOTE #########################################################
        note_menu = tk.Menu(menu, tearoff=False)
        menu.add_cascade(label='Note', underline=0, menu=note_menu)

        self.pinned_checkbutton_var = tk.IntVar()
        note_menu.add_checkbutton(label='Pinned', onvalue=1, offvalue=0, variable=self.pinned_checkbutton_var)

        # NOTES ########################################################
        notes_menu = tk.Menu(menu, tearoff=False)
        menu.add_cascade(label='Notes', underline=1, menu=notes_menu)

        self.sort_mode_var = tk.StringVar()
        for mode in self.sort_modes:
            notes_menu.add_radiobutton(label=f'Sort by {mode}', value=mode, variable=self.sort_mode_var)
        notes_menu.add_separator()
        self.pinned_on_top_var = tk.BooleanVar()
        self.pinned_on_top_var.set(self.config.pinned_ontop)
        notes_menu.add_checkbutton(label='Pinned notes to top',
                                   onvalue=True,
                                   offvalue=False,
                                   variable=self.pinned_on_top_var)

        # SEARCH #######################################################
        search_menu = tk.Menu(menu, tearoff=False)
        menu.add_cascade(label='Search', underline=0, menu=search_menu)

        self.search_mode_options = ("gstyle", "regexp")
        self.search_mode_var = tk.StringVar()

        for mode in self.search_mode_options:
            search_menu.add_radiobutton(label=f'Search mode {mode}', value=mode, variable=self.search_mode_var)

        search_menu.add_separator()

        self.cs_checkbutton_var = tk.IntVar()

        search_menu.add_checkbutton(label='Case sensitive', onvalue=1, offvalue=0, variable=self.cs_checkbutton_var)

        # TOOLS ########################################################
        tools_menu = tk.Menu(menu, tearoff=False)
        menu.add_cascade(label="Tools", underline=0, menu=tools_menu)

        tools_menu.add_command(label="Word Count", underline=0, command=self.word_count)

        tools_menu.add_command(label="List tags", underline=0, command=self.cmd_list_tags)

        # the internet thinks that multiple modifiers should work, but this didn't
        # want to.
        #self.root.bind_all("<Control-Shift-c>", lambda e: self.word_count())

        # HELP ##########################################################
        help_menu = tk.Menu(menu, tearoff=False)
        menu.add_cascade(label="Help", underline='0', menu=help_menu)

        help_menu.add_command(label="About", underline=0, command=self.cmd_help_about)
        help_menu.add_command(label="Bindings", underline=0, command=self.cmd_help_bindings, accelerator="Ctrl+?")

        # END MENU ######################################################

    def _create_ui(self):

        # these two variables determine the final dimensions of our interface
        #FRAME_HEIGHT = 400
        TEXT_WIDTH = 80

        # set the correct class name. this helps your desktop environment
        # to identify the nvPY window.
        self.root = tk.Tk(className="nvPY")

        # setup user-specified TTK theme
        # this HAS to happen after Tk() root has been instantiated, else
        # you'll see errors about PhotoImage not being PhotoImage when we
        # try to set the app icon.
        style = tk.Style()
        #print style.theme_names()
        #print style.theme_use()
        style.theme_use(self.config.theme)

        # Take the last size and position to which the user set the window.
        geo = self.config.read_setting('windows', 'root_geometry')
        if geo:
            self.root['width'] = int(geo.split('x')[0])
            self.root['height'] = int(geo.split("x")[1].split("+")[0])

        self.root.title("nvPY")
        #self.root.configure(background="#b2b2b2")

        # with iconphoto we have to use gif, also on windows
        icon_fn = 'nvpy.gif'
        iconpath = os.path.join(self.config.app_dir, 'icons', icon_fn)

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
        self.statusbar.pack(fill=tk.X, side=tk.BOTTOM, padx=3, pady=3)

        search_frame = tk.Frame(self.root)

        search_entry.make_style()
        self.search_entry_var = tk.StringVar()
        self.search_entry = TriggeredcompleteEntry(search_frame,
                                                   self.config.case_sensitive,
                                                   textvariable=self.search_entry_var,
                                                   style="Search.entry")

        cs_label = tk.Label(search_frame, text="CS ")
        # self.cs_checkbutton_var = tk.IntVar() # Moved to search menu code area
        cs_checkbutton = tk.Checkbutton(search_frame, variable=self.cs_checkbutton_var)

        # self.search_mode_options = ("gstyle", "regexp") # Moved to search menu code area
        # self.search_mode_var = tk.StringVar()
        # I'm working with ttk.OptionVar, which has that extra default param!
        self.search_mode_cb = tk.OptionMenu(search_frame, self.search_mode_var, self.search_mode_options[0],
                                            *self.search_mode_options)
        self.search_mode_cb.config(width=6)

        if not self.config.streamline_interface:
            self.search_mode_cb.pack(side=tk.RIGHT, padx=5)
            cs_checkbutton.pack(side=tk.RIGHT)
            cs_label.pack(side=tk.RIGHT)
        self.search_entry.pack(fill=tk.X, padx=5, pady=5)

        search_frame.pack(side=tk.TOP, fill=tk.X)

        # Recall how the user sized the notes list, if available.
        # The default for width is set in NotesList.__init__() but
        # for height it is set here.
        nl_width = self.config.read_setting('windows', 'notes_list_width') or 30
        nl_height = self.config.read_setting('windows', 'notes_list_height') or 150

        # the paned window ##############################################

        notes_list_config = NotesListConfig(colors=self.config.colors,
                                            layout=self.config.layout,
                                            hide_time=self.config.list_hide_time,
                                            hide_tags=self.config.list_hide_tags,
                                            print_columns=self.config.print_columns)

        if self.config.layout == "horizontal":
            paned_window = tk.PanedWindow(self.root, orient=tk.HORIZONTAL)
            paned_window.pack(fill=tk.BOTH, expand=1)

            list_frame = tk.Frame(paned_window, width=nl_width)
            list_frame.pack_propagate(False)
            paned_window.add(list_frame)

            self.notes_list = NotesList(list_frame, self.config.list_font_family, self.config.list_font_size,
                                        notes_list_config)
            self.notes_list.pack(fill=tk.BOTH, expand=1)

            sort_mode_frame = tk.Frame(list_frame)
            if not self.config.streamline_interface:
                sort_mode_frame.pack(side=tk.TOP, fill=tk.X)
            sort_mode_label = tk.Label(sort_mode_frame, text='Sort by')
            sort_mode_label.pack(side=tk.LEFT)
            sort_mode_selector = tk.OptionMenu(sort_mode_frame, self.sort_mode_var, self.sort_modes[0],
                                               *self.sort_modes)
            sort_mode_selector.pack(side=tk.LEFT, fill=tk.X, expand=1)

            note_frame = tk.Frame(paned_window, width=400)

        else:
            paned_window = tk.PanedWindow(self.root, orient=tk.VERTICAL)
            paned_window.pack(fill=tk.BOTH, expand=1)

            list_frame = tk.Frame(paned_window, height=nl_height)
            list_frame.pack_propagate(0)
            paned_window.add(list_frame)

            if self.config.print_columns == 1:
                font_family = self.config.list_font_family_fixed
            else:
                font_family = self.config.list_font_family

            self.notes_list = NotesList(list_frame, font_family, self.config.list_font_size, notes_list_config)
            self.notes_list.pack(fill=tk.X, expand=1)

            note_frame = tk.Frame(paned_window)

        self.notes_list_frame = list_frame
        paned_window.add(note_frame)

        note_pinned_frame = tk.Frame(note_frame)
        if not self.config.streamline_interface:
            note_pinned_frame.pack(side=tk.BOTTOM, fill=tk.X)

        pinned_label = tk.Label(note_pinned_frame, text="Pinned")
        pinned_label.pack(side=tk.LEFT)
        # self.pinned_checkbutton_var = tk.IntVar() # Moved to note menu code area
        self.pinned_checkbutton = tk.Checkbutton(note_pinned_frame, variable=self.pinned_checkbutton_var)
        self.pinned_checkbutton.pack(side=tk.LEFT)

        note_tags_frame = tk.Frame(note_pinned_frame)
        note_tags_frame.pack(side=tk.LEFT)

        tags_label = tk.Label(note_tags_frame, text="Add Tags")
        tags_label.pack(side=tk.LEFT)

        def completion_func(searchWord):
            if self.taglist is None:
                return []
            tags = [tag for tag in self.taglist if searchWord in tag]
            tags.sort(key=lambda x: x.upper())
            return tags

        self.tags_entry_var = tk.StringVar()
        self.tags_entry = SuggestionEntry(completion_func, note_tags_frame, textvariable=self.tags_entry_var)
        self.tags_entry.pack(side=tk.LEFT, fill=tk.X, expand=1, pady=3, padx=3)

        self.note_existing_tags_frame = tk.Frame(note_tags_frame)
        self.note_existing_tags_frame.pack(side=tk.LEFT)

        # we'll use this method to create the different edit boxes
        def create_scrolled_text(master):
            yscrollbar = tk.Scrollbar(master)
            yscrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            #f = tkFont.nametofont('TkFixedFont')
            f = tkFont.Font(family=self.config.font_family, size=self.config.font_size)
            # tkFont.families(root) returns list of available font family names
            # this determines the width of the complete interface (yes)
            text = TriggeredcompleteText(master,
                                         self.config.case_sensitive,
                                         height=25,
                                         width=TEXT_WIDTH,
                                         wrap=tk.WORD,
                                         font=f,
                                         tabs=(4 * f.measure(0), 'left'),
                                         tabstyle='wordprocessor',
                                         yscrollcommand=yscrollbar.set,
                                         undo=True,
                                         foreground=self.config.colors.text,
                                         background=self.config.colors.background,
                                         insertbackground=self.config.colors.text)
            # change default font at runtime with:
            text.config(font=f)

            # need expand=1 so that when user resizes window, text widget gets the extra space
            text.pack(fill=tk.BOTH, expand=1)

            #xscrollbar.config(command=text.xview)
            yscrollbar.config(command=text.yview)

            return text

        # setup user_text ###############################################
        self.text_note = create_scrolled_text(note_frame)
        self.fonts = self.notes_list.fonts + self.text_note.fonts

        # setup generic tags for markdown highlighting
        bold_font = tkFont.Font(self.text_note, self.text_note.cget("font"))
        bold_font.configure(weight="bold")
        self.text_note.tag_config('md-bold', font=bold_font)
        self.fonts.append(bold_font)

        # finish UI creation ###########################################

        # set the window to the same place that it was last time
        geo = self.config.read_setting('windows', 'root_geometry')
        if geo:
            self.root.geometry(geo)
        else:
            # now set the minsize so that things can not disappear
            self.root.minsize(self.root.winfo_width(), self.root.winfo_height())

        # call update so we know that sizes are up to date
        self.root.update_idletasks()

    def get_number_of_notes(self):
        return self.notes_list.get_number_of_notes()

    def handler_close(self, evt=None):
        """Handler for exit menu command and close window event.
        """
        # Save window positions and notes list width or height.
        geo = self.root.geometry()
        nl_width = self.notes_list_frame.winfo_width()
        nl_height = self.notes_list_frame.winfo_height()
        self.config.write_setting('windows', 'root_geometry', geo)
        if self.config.layout == 'horizontal':
            self.config.write_setting('windows', 'notes_list_width', nl_width)
        if self.config.layout == 'vertical':
            self.config.write_setting('windows', 'notes_list_height', nl_height)

        self.notify_observers('close', None)

    def clear_note_ui(self, silent=True):
        """Called when no note has been selected.

        Should give the user clear indication that no note has been selected,
        hence no note editing actions can be taken.

        @param silent: The default is not to fire any event handlers when
        clearing the note.
        @return:
        """

        # ascii art created with: http://patorjk.com/software/taag/

        msg = """
        No note currently selected.

        Either select a note, or press Ctrl-N to create
        a new note titled with the current search string,
        or modify the search string.

        .__   __. ____    ____ .______   ____    ____
        |  \ |  | \   \  /   / |   _  \  \   \  /   /
        |   \|  |  \   \/   /  |  |_)  |  \   \/   /
        |  . `  |   \      /   |   ___/    \_    _/
        |  |\   |    \    /    |  |          |  |
        |__| \__|     \__/     | _|          |__|


        """

        if silent:
            self.mute_note_data_changes()

        self.text_note.delete(1.0, tk.END)  # clear all
        self.text_note.insert(1.0, msg)
        self.tags_entry_var.set('')

        self.statusbar.set_note_status('No note selected.')

        if silent:
            self.unmute_note_data_changes()

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
        tkMessageBox.showinfo('Help | About',
                              'nvPY %s - A rather ugly but cross-platform simplenote client.\n\n'
                              'Copyright 2017-2022 yuuki0xff <https://yuuki0xff.jp/>\n'
                              'Copyright 2012-2016 Charl P. Botha <http://charlbotha.com/>\n' %
                              (self.config.app_version, ),
                              parent=self.root)

    def cmd_list_tags(self):
        l = TagList(self.root, self.taglist, self)
        self.root.wait_window(l)

    def cmd_help_bindings(self):
        h = HelpBindings()
        self.root.wait_window(h)

    def cmd_rest(self, event=None):
        self.notify_observers('command:rest', None)

    def cmd_sync_current_note(self, event=None):
        self.notify_observers('command:sync_current_note', None)

    def cmd_sync_full(self, event=None):
        self.notify_observers('command:sync_full', None)

    def cmd_font_size(self, inc_size):
        for f in self.fonts:
            f.configure(size=f['size'] + inc_size)

    def handler_cs_checkbutton(self, *args):
        self.notify_observers('change:cs', events.CheckboxChangedEvent(value=self.cs_checkbutton_var.get()))

    def handler_housekeeper(self):
        try:
            # nvPY will do saving and syncing!
            self.notify_observers('keep:house', None)
            self.after(self.config.housekeeping_interval_ms, self.handler_housekeeper)
        except Exception as e:
            self.show_error('Housekeeper error', 'An error occurred during housekeeping.\n' + str(e))
            raise

    def toggle_pinned_checkbutton(self):
        self.pinned_checkbutton_var.set(not self.pinned_checkbutton_var.get())
        self.handler_pinned_checkbutton()

    def handler_pinned_checkbutton(self, *args):
        self.notify_observers('change:pinned', events.CheckboxChangedEvent(value=self.pinned_checkbutton_var.get()))

    def handler_search_enter(self, evt):
        # user has pressed enter whilst searching
        # 1. if a note is selected, focus that
        # 2. if nothing is selected, create a new note with this title

        if self.notes_list.selected_idx >= 0:
            self.text_note.focus()
            self.text_note.see(tk.INSERT)

        else:
            # nothing selected
            self.notify_observers('create:note', events.NoteCreatedEvent(title=self.get_search_entry_text()))
            # the note will be created synchronously, so we can focus the text area already
            self.text_note.focus()

    def handler_search_escape(self, evt):
        # user has pressed escape whilst searching
        # 1. if search box has text in it, delete that text
        # 2. if search box does not have text in it and the user has configured escape_to_exit, then quit

        if self.get_search_entry_text() != '':
            self.search_entry.delete(0, tk.END)

        elif self.config.escape_to_exit:
            self.handler_close()

    def handler_search_entry(self, *args):
        self.notify_observers('change:entry', events.TextBoxChangedEvent(value=self.search_entry_var.get()))

    def handler_search_mode(self, *args):
        """
        Called when the user changes the search mode via the OptionMenu.

        This will also be called even if the user reselects the same option.

        @param args:
        @return:
        """
        self.notify_observers('change:search_mode', events.CheckboxChangedEvent(value=self.search_mode_var.get()))

    def handler_add_tags_to_selected_note(self, evt=None):
        self.notify_observers('add:tag', events.TagsAddedEvent(tags=self.tags_entry_var.get()))

    def handler_click_link(self, link):
        if link.startswith('[['):
            link = link[2:-2]
            self.notify_observers('click:notelink', link)

        else:
            if platform.system().lower() == 'windows':
                os.startfile(link)
            elif platform.system().lower() == 'darwin':
                subprocess.call(('open', link))
            else:
                subprocess.call(('xdg-open', link))

    def activate_search_string_highlights(self):
        # no note selected, so no highlights.
        if self.notes_list.selected_idx < 0:
            return

        t = self.text_note

        # remove all existing tags
        for tag in self.text_tags_search:
            t.tag_remove(tag, '1.0', 'end')

        del self.text_tags_search[:]

        st = self.notes_list_model.match_regexp
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
            tag = 'search-%d' % (len(self.text_tags_search), )
            t.tag_config(tag, background=self.config.colors.highlight_background)

            # mo.start(), mo.end() or mo.span() in one go
            t.tag_add(tag, '1.0+%dc' % (mo.start(), ), '1.0+%dc' % (mo.end(), ))

            # record the tag name so we can delete it later
            self.text_tags_search.append(tag)

    def activate_links(self):
        """
        Also see this post on URL detection regular expressions:
        http://www.regexguru.com/2008/11/detecting-urls-in-a-block-of-text/
        (mine is slightly modified)
        """

        t = self.text_note

        # Remove all existing tags
        for tag in self.text_tags_links:
            t.tag_remove(tag, '1.0', 'end')

        del self.text_tags_links[:]

        # List of Regex patterns to match various link types to be activated
        re_list = [
            r"(\[\[[^][]*\]\])",  # Inter-note Links
            r"((?:https?|ftp|file)://[-A-Za-z0-9+&@#/%?=~_|!:,.;\(\)]*[A-Za-z0-9+&@#/%=~_|])",  # Http(s) / FTP / File Links
            r"(mailto:[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)",  # Mailto Links
            r"((?:tel|mid):[^\s]+)",  # Tel / Mid Links
            r"((?:thunderlink|irc|ircs|irc6)://[^\s]+)",  # Thunderbird and IRC Links
            r"(message:(?://)?(?:%3c|<).*(?:%3e|>))"  # Leopard Mail Message Links
        ]

        # Compile Regex into single pattern
        pat = re.compile('|'.join(re_list))

        for mo in re.finditer(pat, t.get('1.0', 'end')):
            # Any Match in Group 0 is a Note Link
            if mo.groups()[0] is not None:
                link = mo.groups()[0]
                ul = 0
            else:
                link = list(filter(None, mo.groups()))[0]
                ul = 1

            # Create a new Tkinter Tag
            tag = 'web-%d' % (len(self.text_tags_links), )
            t.tag_config(tag,
                         foreground=self.config.colors.url,
                         selectbackground=self.config.colors.url_selection_background,
                         underline=ul)

            # Hovering over link changes cursor to hand
            t.tag_bind(tag, '<Enter>', lambda e: t.config(cursor="hand2"))
            t.tag_bind(tag, '<Leave>', lambda e: t.config(cursor=""))

            # Clicking link calls link handler method
            t.tag_bind(tag, '<Button-1>', lambda e, link=link: self.handler_click_link(link))

            # record the tag name so we can delete it later
            self.text_tags_links.append(tag)

            # mo.start(), mo.end() or mo.span() in one go
            t.tag_add(tag, '1.0+%dc' % (mo.start(), ), '1.0+%dc' % (mo.end(), ))

    def activate_markdown_highlighting(self):
        t = self.text_note
        content = t.get('1.0', 'end')

        # we have multiple tags with the same name, e.g. md-bold
        # this will remove all of them.
        t.tag_remove('md-bold', '1.0', 'end')

        # first just use our standard regular expression for finding the first
        # non whitespace line, wherever it is:
        mo = utils.note_title_re.match(content)
        if mo:
            t.tag_add('md-bold', '1.0+{0}c'.format(mo.start()), '1.0+{0}c'.format(mo.end()))

        # then do headings
        pat = re.compile(r"^#.*$", re.MULTILINE)

        for mo in pat.finditer(content):
            # mo.start(), mo.end() or mo.span() in one go
            t.tag_add('md-bold', '1.0+{0}c'.format(mo.start()), '1.0+{0}c'.format(mo.end()))

    def handler_control_backspace(self, evt):
        if self.text_note.index("insert-1c") != "1.0" and self.text_note.index(tk.INSERT) != "1.0":
            if self.text_note.index("insert wordstart-1c") == "1.0":
                i = 0
                while self.text_note.index(tk.INSERT) != "1.0" and i < 25:
                    self.text_note.delete("insert-1c")
                    i += 1
            else:
                insertm1c = self.text_note.get("insert-1c")
                while insertm1c in "  " and insertm1c != "":
                    self.text_note.delete("insert-1c")
                    insertm1c = self.text_note.get("insert-1c")
                if insertm1c in "\n\t.?!,@#…¿/\\\"'—–" and insertm1c != "":
                    i = 0
                    while (insertm1c in "\n\t.?!,@#…¿/\\\"'—–" and insertm1c != "") and i < 25:
                        self.text_note.delete("insert-1c")
                        insertm1c = self.text_note.get("insert-1c")
                        i += 1
                else:
                    while insertm1c not in "\n\t  .?!,@#…¿/\\\"'—–" and insertm1c != "":
                        self.text_note.delete("insert-1c")
                        insertm1c = self.text_note.get("insert-1c")
        return "break"

    def handler_control_delete(self, evt):
        insert = self.text_note.get(tk.INSERT)
        if insert in "  " and insert != "":
            while insert in "  " and insert != "":
                self.text_note.delete(tk.INSERT)
                insert = self.text_note.get(tk.INSERT)
        elif insert not in "\n\t  .?!,@#…¿/\\\"'—–":
            while insert not in "\n\t  .?!,@#…¿/\\\"'—–":
                self.text_note.delete(tk.INSERT)
                insert = self.text_note.get(tk.INSERT)
            if insert in "  ":
                while insert in "  " and insert != "":
                    self.text_note.delete(tk.INSERT)
                    insert = self.text_note.get(tk.INSERT)
        else:
            if insert in "\n\t" and insert != "":
                if self.text_note.get(
                        tk.INSERT,
                        tk.END).strip() == "" and self.text_note.index(tk.INSERT) != self.text_note.index(tk.END):
                    self.text_note.delete(tk.INSERT, tk.END)
                else:
                    while insert in "\n\t  " and insert != "":
                        self.text_note.delete(tk.INSERT)
                        insert = self.text_note.get(tk.INSERT)
            else:
                self.text_note.delete(tk.INSERT)
        return "break"

    def handler_text_change(self, evt):
        self.notify_observers('change:text', None)
        # FIXME: consider having this called from the housekeeping
        # handler, so that the poor regexp doesn't have to do every
        # single keystroke.
        self.activate_links()
        self.activate_search_string_highlights()
        self.activate_markdown_highlighting()

    def handler_text_copy(self, event):
        first = self.text_note.index('sel.first')
        last = self.text_note.index('sel.last')
        if first and last:
            # Propagate event to other handlers.
            return
        # Nothing selected. Copy the note title.
        self.notes_list.cmd_text_copy(event)
        return 'break'

    def handler_sort_mode_change(self, *args):
        self.notify_observers('change:sort_mode', events.SortModeChangedEvent(self.sort_mode_var.get()))

    def handler_pinned_on_top_change(self, *args):
        self.notify_observers('change:pinned_on_top', events.PinnedOnTopChangedEvent(self.pinned_on_top_var.get()))

    def is_note_different(self, note):
        """
        Determine if note would cause a UI update.
        """

        if self.get_text() != note.get('content'):
            return True

        tags = note.get('tags', [])

        # get list of string tags from ui
        tag_elements = self.note_existing_tags_frame.children.values()
        ui_tags = [element['text'].replace(' x', '') for element in tag_elements]

        if sorted(ui_tags) != sorted(tags):
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
        self.mute('add:tag')
        self.mute('delete:tag')
        self.mute('change:pinned')

    def search(self, e):
        self.search_entry.focus()
        self.search_entry.selection_range(0, tk.END)

    def set_cs(self, cs, silent=False):
        if silent:
            self.mute('change:cs')

        self.cs_checkbutton_var.set(cs)

        self.unmute('change:cs')

    def set_search_mode(self, search_mode, silent=False):
        """

        @param search_mode: the search mode, "gstyle" or "regexp"
        @param silent: Specify True if you don't want the view to trigger any events.
        @return:
        """

        if silent:
            self.mute('change:search_mode')

        self.search_mode_var.set(search_mode)

        self.unmute('change:search_mode')

    def set_status_text(self, txt):
        self.statusbar.set_status(txt)

    def handler_delete_tag_from_selected_note(self, tag_name):
        self.notify_observers('delete:tag', events.TagRemovedEvent(tag=tag_name))

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
            self.text_note.delete(1.0, tk.END)  # clear all

        if note is not None:
            if not content_unchanged:
                self.text_note.insert(tk.END, note['content'])

            # default to an empty array for tags
            tags = note.get('tags', [])

        else:
            # note is None - for tags machinery further down, we have empty list
            tags = []

        tag_button_list = list(self.note_existing_tags_frame.children.values())
        for tag_button in tag_button_list:
            tag_button.destroy()

        for tag in tags:
            tag_button = tk.Button(self.note_existing_tags_frame,
                                   width=0,
                                   text=tag + " x",
                                   command=lambda tag=tag: self.handler_delete_tag_from_selected_note(tag))
            tag_button.pack(side=tk.LEFT)

        if note is not None:
            self.pinned_checkbutton_var.set(utils.note_pinned(note))

        if reset_undo:
            # usually when a new note is selected, we want to reset the
            # undo buffer, so that a user can't undo right into the previously
            # selected note.
            self.text_note.edit_reset()

    def set_notes(self, notes):
        # this method is called by View.observer_notes_list()

        # clear the notes list
        self.notes_list.clear()
        taglist = []
        titlelist = []

        for o in notes:
            tags = o.note.get('tags')
            if tags:
                taglist += tags

            self.notes_list.append(o.note, NoteConfig(tagfound=o.tagfound))
            # find first non-empty line, and append to titlelist.
            for title in o.note["content"].splitlines():
                slim_title = title.strip()
                if slim_title:
                    titlelist.append(slim_title)
                    break

        titlelist = list(set(titlelist))
        self.text_note.set_completion_list(titlelist)

        if self.taglist is None:
            # first time we get called, so we need to initialise
            self.taglist = list(set(taglist))
            self.search_entry.set_completion_list(self.taglist)

        else:
            # only set completion list if the new combined taglist is larger.
            taglist = list(set(self.taglist + taglist))
            if len(taglist) > len(self.taglist):
                self.taglist = taglist
                self.search_entry.set_completion_list(self.taglist)

    def show_error(self, title, msg):
        tkMessageBox.showerror(title, msg)

    def show_info(self, title, msg):
        tkMessageBox.showinfo(title, msg, parent=self.root)

    def show_warning(self, title, msg):
        tkMessageBox.showwarning(title, msg)

    def unmute_note_data_changes(self):
        self.unmute('change:text')
        self.unmute('add:tag')
        self.unmute('delete:tag')
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

        self.show_info('Word Count', '%d words in total\n%d words in selection' % (tlen, slen))

    def after(self, ms, callback):
        timer_id = 'dummy_value'

        def fn():
            with self.timer_ids_lock:
                # timer_id is updated to actual value by self.root.after().
                self.timer_ids.remove(timer_id)

            callback()

        with self.timer_ids_lock:
            timer_id = self.root.after(ms, fn)
            self.timer_ids.add(timer_id)
            return timer_id

    def cancel_timers(self):
        with self.timer_ids_lock:
            for timer_id in self.timer_ids:
                self.root.after_cancel(timer_id)
