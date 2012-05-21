# nvPY: cross-platform note-taking app with simplenote syncing
# copyright 2012 by Charl P. Botha <cpbotha@vxlabs.com>
# new BSD license

import os
import search_entry
import tk
import tkMessageBox
import utils

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

class View(utils.SubjectMixin):
    """Main user interface class.
    """
    
    def __init__(self, config, notes_list_model):
        utils.SubjectMixin.__init__(self)
        
        self.config = config
        
        notes_list_model.add_observer('set:list', self.observer_notes_list)
        self.notes_list_model = notes_list_model
        
        self.root = None

        self._create_ui()
        self._bind_events()

        #self._current_text = None
        #self.user_text.focus_set()

        self.search_entry.focus_set()
        
    def cmd_lb_notes_select(self, evt):
        sidx = self.get_selected_idx()
        self.notify_observers('select:note', utils.KeyValueObject(sel=sidx))
        
    def cmd_root_delete(self, evt):
        sidx = self.get_selected_idx()
        self.notify_observers('delete:note', utils.KeyValueObject(sel=sidx))
        
    def cmd_root_new(self, evt):
        # this'll get caught by a controller event handler
        self.notify_observers('create:note', utils.KeyValueObject(title=self.get_search_entry_text()))
        # the note will be created synchronously, so we can focus the text area already
        self.text_note.focus()
        
    def get_selected_idx(self):
        # no selection: s = ()
        # something: s = ('idx',)
        s = self.lb_notes.curselection()
        sidx = int(s[0]) if s else -1
        return sidx
    
    def get_text(self):
        # err, you have to specify 1.0 to END, and NOT 0 to END like I thought.
        return self.text_note.get(1.0, tk.END)
    
    def get_search_entry_text(self):
        return self.search_entry_var.get()
    
    def refresh_notes_list(self):
        """Trigger a complete refresh notes list by resetting search entry,
        selected note, and cursor position within that note.
        """
        # store cursor position first! returns e.g. 8.32
        cursor_pos = self.text_note.index(tk.INSERT)
        self.set_search_entry_text(self.get_search_entry_text())
        self.select_note(self.get_selected_idx(), silent=True)
        self.text_note.mark_set(tk.INSERT, cursor_pos)

    def select_note(self, idx, silent=False):
        # programmatically select the note by idx
        self.lb_notes.select_clear(0, tk.END)
        self.lb_notes.select_set(idx)
        # we move the active (underlined) selection along, else we lose
        # synchronization during arrow movements with the search entry selected
        self.lb_notes.activate(idx)
        if not silent:
            # we have to generate event explicitly, it doesn't fire by itself in this case
            self.lb_notes.event_generate('<<ListboxSelect>>')
        
    def select_note_prev(self):
        idx = self.get_selected_idx()
        if idx > 0:
            self.select_note(idx - 1)
    
    def select_note_next(self):
        idx = self.get_selected_idx()
        # self.lb_notes.index(tk.END) returns the number of items
        if idx < self.lb_notes.index(tk.END) - 1:
            self.select_note(idx + 1)
            
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
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        
        self.root.bind_all("<Control-d>", self.cmd_root_delete)
        self.root.bind_all("<Control-f>", lambda e: self.search_entry.focus())
        self.root.bind_all("<Control-n>", self.cmd_root_new)
        
        self.lb_notes.bind("<<ListboxSelect>>", self.cmd_lb_notes_select)
        # same behaviour as when the user presses enter on search entry:
        # if something is selected, focus the text area
        # if nothing is selected, try to create new note with
        # search entry value as name
        self.lb_notes.bind("<Return>", self.handler_search_enter)        
        
        self.search_entry.bind("<Escape>", lambda e:
                self.search_entry.delete(0, tk.END))
        # this will either focus current content, or
        # if there's no selection, create a new note.
        self.search_entry.bind("<Return>", self.handler_search_enter)
        
        self.search_entry.bind("<Up>", lambda e:
                               self.select_note_prev())
        self.search_entry.bind("<Down>", lambda e:
                               self.select_note_next())
        
        self.text_note.bind("<<Change>>", self.handler_text_change)
        
        # user presses escape in text area, they go back to notes list
        self.text_note.bind("<Escape>", lambda e: self.lb_notes.focus())
        # <Key>
        
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
        file_menu.add_command(label = "Sync full", underline=0,
                              command=self.cmd_sync_full, accelerator="Ctrl-S")
        self.root.bind_all("<Control-s>", self.cmd_sync_full)
        
        file_menu.add_command(label = "Exit", underline=1,
                              command=self.cmd_exit, accelerator="Ctrl+Q")
        self.root.bind_all("<Control-q>", self.cmd_exit)

        # EDIT ##########################################################
        edit_menu = tk.Menu(menu, tearoff=False)
        menu.add_cascade(label="Edit", underline=0, menu=edit_menu)
        
        edit_menu.add_command(label="Cut", accelerator="Ctrl+X",
                              underline=2, command=self.cmd_cut)
        edit_menu.add_command(label="Copy", accelerator="Ctrl+C",
                              underline=0, command=self.cmd_copy)
        edit_menu.add_command(label="Paste", accelerator="Ctrl+V",
                              underline=0, command=self.cmd_paste)


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
        
        self.root = tk.Tk()
        self.root.title("nvPY")
        #self.root.configure(background="#b2b2b2")

        # try finding icon in resdir and in appdir
        try:
            iconpath = os.path.join(
                self.config.app_dir, 'icons', 'nvpy.ico')
            self.root.iconbitmap(bitmap=iconpath, default=iconpath)
            
        except tk.TclError:
            pass

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
        self.search_entry = tk.Entry(search_frame, textvariable=self.search_entry_var, style="Search.entry")
        self.search_entry_var.trace('w', self.handler_search_entry)
        self.search_entry.pack(fill=tk.X,padx=5, pady=5)
        search_frame.pack(side=tk.TOP, fill=tk.X)
        
        
        # the paned window ##############################################
        paned_window = tk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=1)
        
        left_frame = tk.Frame(paned_window, width=100)
        paned_window.add(left_frame)
        
        self.lb_notes = tk.Listbox(left_frame)
        
        # need both fill and expand to make it fill all avail area
        self.lb_notes.pack(fill=tk.BOTH, expand=1)

        right_frame = tk.Frame(paned_window, width=400)
        paned_window.add(right_frame)

        # we'll use this method to create the different edit boxes
        def create_scrolled_text(master):
            yscrollbar = tk.Scrollbar(master)
            yscrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            # this determines the width of the complete interface (yes)
            text = RedirectedText(master, height=25, width=TEXT_WIDTH,
                                  wrap=tk.CHAR,
                                  yscrollcommand=yscrollbar.set)

            text.pack(fill=tk.BOTH, expand=1)

            #xscrollbar.config(command=text.xview)
            yscrollbar.config(command=text.yview)

            return text


        # setup user_text ###############################################
        self.text_note = create_scrolled_text(right_frame)

#        def cb_ut_fi(event):
#            self.set_current_text(CURTEXT_USER)
#
#        self.user_text.bind('<FocusIn>', cb_ut_fi)
#
#        def cb_ut_m(event):
#            self.set_user_mode(MODE_MODIFIED)
#
#        self.user_text.bind('<<Change>>', cb_ut_m)
#
#        # setup sys_text ################################################
#        self.sys_text, self._sys_mode_label_var = \
#                      create_scrolled_text(bottom_frame, "System Environment")
#
#        def cb_st_fi(event):
#            self.set_current_text(CURTEXT_SYS)
#
#        self.sys_text.bind('<FocusIn>', cb_st_fi)
#
#        def cb_st_c(event):
#            self.set_sys_mode(MODE_MODIFIED)
#            
#        self.sys_text.bind('<<Change>>', cb_st_c)

        # finish UI creation ###########################################

        # now set the minsize so that things can not disappear
        self.root.minsize(self.root.winfo_width(), self.root.winfo_height())
        
        # call update so we know that sizes are up to date
        self.root.update_idletasks()
        
        
    def close(self):
        self.notify_observers('close', None)
        self.root.destroy()


    def cmd_cut(self):
        self.text_note.event_generate('<<Cut>>')

    def cmd_copy(self):
        self.text_note.event_generate('<<Copy>>')
        
    def cmd_paste(self):
        self.text_note.event_generate('<<Paste>>')


    def cmd_help_about(self):
        tkMessageBox.showinfo(
            'Help | About',
            'nvPY %s is copyright 2012 by Charl P. Botha '
            '<http://charlbotha.com/>\n\n'
            'A rather ugly but cross-platform simplenote client.' % (self.config.app_version,),
            parent = self.root)

    def cmd_exit(self, event=None):
        self.close()
        
    def cmd_sync_full(self, event=None):
        self.notify_observers('command:sync_full', None)
        
    def handler_housekeeper(self):
        # nvPY will do saving and syncing!
        self.notify_observers('keep:house', None)
        
        # check if titles need refreshing
        refresh_notes_list = False
        prev_title = None
        prev_modifydate = None
        for i,o in enumerate(self.notes_list_model.list):
            # order should be the same as our listbox
            nt = utils.get_note_title(o.note)
            ot = self.lb_notes.get(i)
            # if we strike a note with an out-of-date title, redo.
            if nt != ot:
                print "title out of date"
                refresh_notes_list = True
                continue
            
            if self.config.sort_mode == 0:
                # alpha
                if prev_title is not None and prev_title > nt:
                    print "alpha resort"
                    refresh_notes_list = True
                    continue
                
                prev_title = nt
                
            else:
                md = float(o.note.get('modifydate', 0))
                if prev_modifydate is not None and prev_modifydate < md:
                    print "modifydate resort"
                    refresh_notes_list = True
                    continue
                
                prev_modifydate = md 
            
        if refresh_notes_list:
            self.refresh_notes_list()
        
        self.root.after(self.config.housekeeping_interval_ms, self.handler_housekeeper)
        
    def handler_search_enter(self, evt):
        # user has pressed enter whilst searching
        # 1. if a note is selected, focus that
        # 2. if nothing is selected, create a new note with this title

        if self.get_selected_idx() >= 0:
            self.text_note.focus()
            
        else:
            # nothing selected
            self.notify_observers('create:note', utils.KeyValueObject(title=self.get_search_entry_text()))
            # the note will be created synchronously, so we can focus the text area already
            self.text_note.focus()
        
    def handler_search_entry(self, *args):
        self.notify_observers('change:entry', 
                              utils.KeyValueObject(value=self.search_entry_var.get()))
        
    def handler_text_change(self, evt):
        self.notify_observers('change:text', None)
                
    def observer_notes_list(self, notes_list_model, evt_type, evt):
        if evt_type == 'set:list':
            # re-render!
            self.set_notes(notes_list_model.list)
            
    def main_loop(self):
        self.root.mainloop()
        
    def set_status_text(self, txt):
        self.statusbar.set_status(txt)
        
    def set_text(self, note_content):
        self.text_note.delete(1.0, tk.END) # clear all
        self.text_note.insert(tk.END, note_content)
        
        
    def set_notes(self, notes):
        # clear the listbox
        self.lb_notes.delete(0, tk.END)
        
        for o in notes:
            self.lb_notes.insert(tk.END, utils.get_note_title(o.note))

    def show_error(self, title, msg):
        tkMessageBox.showerror(title, msg)
        
