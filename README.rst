====
nvPY
====

nvpy is a simplenote-syncing note-taking tool inspired by Notational
Velocity (and a little bit by nvALT too) on OSX and ResophNotes on
Windows. It is significantly uglier, but it is cross-platform.  Yes,
you heard right, you can run this on Linux (tested), Windows (tested)
and OS X (lightly tested).

It was written by Charl Botha, who needed a simplenote client on Linux and doesn't mind ugliness (that much). Sjaak Westdijk has contributed significantly to the codebase since right after the 0.8.5 release.

* nvpy lives happily at https://github.com/cpbotha/nvpy
* For news and discussion, join the `public nvpy google group <https://groups.google.com/d/forum/nvpy>`_ or subscribe to its `RSS topic feed <https://groups.google.com/group/nvpy/feed/rss_v2_0_topics.xml>`_.

DISCLAIMER
==========
If nvpy blows up your computer, loses your job or just deletes all
your notes, I am NOT liable for anything. Also see the liability
clause at the end of the new BSD licence text in the COPYRIGHT file.

That being said, I use nvpy daily on my own precious notes database
and it hasn't disappointed me (yet).

Screenshots and screencasts
===========================

* Screenshot taken shortly after 0.9.3 release:

.. image:: https://lh4.googleusercontent.com/-ASCgH2VhYmc/UIOlIWLvYVI/AAAAAAAAQ8s/0ccEQLHXKIg/s800/nvpy_post_0.9.2_screenshot.png

* Screencast of nvpy's inter-note linking (May 27, 2012): http://youtu.be/NXuVMZr31SI
* Screencast of nvpy's gstyle search mode (October 18, 2012): http://youtu.be/dzILoLC5vRM
* `Picasa Web album containing various screenshots over time <https://picasaweb.google.com/102438662851504788261/NvpyPublic?authuser=0&feat=directlink>`_.

A note on automatic syncing
===========================

* When nvPY starts up, it automatically performs a full sync. When you start it up for the first time, this can take quite a while. On subsquent startups, it's much faster, as it maintains its own database on disk.
* While running, nvPY automatically and continuously saves and syncs any changes to disk and to simplenote. You don't have to do anything besides typing your notes.
* If you edit the same note simultaneously in nvPY and for example the web interface, these changes will be merged as you work.
* If you add or delete notes from a completely different location, nvPY will not pick this up until your next full sync. In the future, this will also happen automatically.
* In short: You usually don't have to worry about syncing and saving, simplenote takes care of this. If you have any more questions, please post them in the `nvpy google group <https://groups.google.com/d/forum/nvpy>`_.

Installation
============

nvPY works best on Python 2.7.x. It does not work on Python 3.x yet.

To install the latest development version from github, do::

    pip install git+https://github.com/cpbotha/nvpy.git#egg=nvpy

OR, to install the version currently on pypi, do::

    pip install nvpy
    
If already have nvpy installed, but you want to upgrade, try the following::

    sudo pip uninstall nvpy
    sudo pip install --upgrade --ignore-installed --no-deps nvpy

OR, you can of course use easy\_install instead::

    easy_install nvpy

github always has the latest development version, whereas I upload
tagged snapshots (v0.9 for example) to pypi.

For more detailed installation recipes, also for beginners, and for instructions on how to integrate nvPY with your Linux desktop environment, see the `nvPY installation guide <https://github.com/cpbotha/nvpy/blob/master/docs/installation.rst>`_.

How to run for the first time
=============================

Create a file called .nvpy.cfg in your home directory that looks like
the following::

    [nvpy]
    sn_username = your_simplenote_username
    sn_password = your_simplenote_password

If you installed this via pip install, you should now be able to start
the application by typing "nvpy". The first time you run it, it will take
a while as it downloads all of your simplenote notes. Subsequent runs
are much faster as it uses the database it stores in your home directory.

If you prefer to run from your git clone, you can just invoke python on nvpy.py, or on the nvpy package directory.

The `example nvpy.cfg <https://github.com/cpbotha/nvpy/blob/master/nvpy/nvpy-example.cfg>`_ shows how you can configure the font 
family and size, configure nvpy to save and load notes as clear text, disable simplenote syncing, and so forth.

Keyboard handling
=================

nvPY was designed for lightning-speed note-taking and management with
the keyboard. As you type words in the search bar, the list of notes
found will be refined. In the default search mode ("gstyle"), it finds
notes that contain all the words you enter. For example::

    t:work t:leads python imaging "exact phrase"

Will find all notes tagged with both "work" and "leads" containing the
words "python" and "imaging" (anywhere, and in any order) and the exact
phrase "exact phrase". The default is to search with case-sensitivity.
This can be changed with the CS checkbox. Remember though that
case-sensitivity has a significant effect on search speed.

By editing the config file, or by toggling the search mode option menu,
you can use regular expression search mode. This is of course much more
powerful, but is much slower than gstyle. The difference is noticeable
on large note collections.

Here's a summary of the different shortcut keys that you can use in nvPY:

========== ==========
Key combo  Action
========== ==========
Ctrl-?     Display these key-bindings.
Ctrl-A     Select all text when in the note editor.
Ctrl-D     Move note to trash. This can be easily recovered using the simplenote webapp.
Ctrl-F     Start real-time incremental regular expression search. As you type, notes list is filtered. Up / down cursor keys go to previous / next note.
Ctrl-G     Edit tags for currently selected note. Press ESC to return to note editing.
Ctrl-M     Render Markdown note to HTML and open browser window.
Ctrl-N     Create new note.
Ctrl-Q     Exit nvPY.
Ctrl-R     Render reStructuredText (reST) note to HTML and open browser window.
Ctrl-S     Force sync of current note with simplenote server. Saving to disc and syncing to server also happen continuously in the background.
Ctrl-Y     Redo note edits.
Ctrl-Z     Undo note edits.
Ctrl-SPACE In search box, autocomplete tag under cursor. Keep on pressing for more alternatives.
Ctrl-+/-   Increase or decrease the font size.
ESC        Go from edit mode to notes list.
ENTER      Start editing currently selected note. If there's a search string but no notes in the list, ENTER creates a new note with that search string as its title.
========== ==========

Features
========

* Syncs with simplenote.
* Support for simplenote tags and note pinning.
* Partial syncs (whilst notes are being edited) are done by a
  background thread so you can keep on working at light speed.
* Can be used offline, also without simplenote account.
* Search box does realtime gstyle or regular expression searching in all your
  notes. All occurrences of the search string are also
  highlighted in currently active note.
* Markdown rendering to browser.
* Continuous rendering mode: If you activate this before
  starting the markdown rendering, nvpy will render new html of
  the currently open note every few seconds. Due to the refresh
  tag in the generated HTML, the browser will refresh every few
  seconds. MAGIC UPDATES!
* reStructuredText (reST) rendering to browser. Yes, you can use nvPY
  as your reST previewer.
* Automatic hyperlink highlighting in text widget.
* KickAss(tm) inter-note linking with [[note name]]. If note name is
  not found in current list of notes, assumes it's a regular expression
  and sets it in the search bar. See the `screencast <http://youtu.be/NXuVMZr31SI>`_.

Planned features
================

* Full(ish) screen mode.
* Full syncs also in background thread. At the moment does a full sync
  at startup, which can take a while. nvpy already does background thread
  saving and syncing while you work, so everything you type is backed up
  within a few seconds of you typing it.
* Prettiness.

Bugs and feedback
=================

* Report bugs with `the github issue tracker <https://github.com/cpbotha/nvpy/issues>`_.
* It's an even better idea to clone, fix and then send me a pull request.
* If you have questions, or would like to discuss nvpy-related matters, please do so via the `nvpy google discussion group / mailing list <https://groups.google.com/d/forum/nvpy>`_.
* If you really like nvpy, you could make me and you even happier by `tipping me with paypal <https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=BXXTJ9E97DG52>`_! 

Credits
=======

* Sjaak Westdijk made significant contributions to the code starting after the 0.8.5 release.
* nvpy uses the `fantastic simplenote.py library by mrtazz <https://github.com/mrtazz/simplenote.py>`_.
* The brilliant application icon, a blue mini car (not as fast as the notational velocity rocket, get it?), is by `Cemagraphics <http://cemagraphics.deviantart.com/>`_.
* Thanks for the tips! stfa and https://github.com/gudnm

