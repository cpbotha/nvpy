====
nvPY
====

nvpy is a simplenote-syncing note-taking tool inspired by nvALT (OS X)
and ResophNotes (Windows). It is significantly uglier, but it is
cross-platform.  Yes, you heard right, you can run this on Linux
(tested), Windows (tested) and OS X (in theory).

It was written by Charl Botha, who needed a simplenote client on
Linux and doesn't mind ugliness (that much). nvpy lives happily at
https://github.com/cpbotha/nvpy

DISCLAIMER
==========
If nvpy blows up your computer, loses your job or just deletes all
your notes, I am NOT liable for anything. Also see the liability
clause at the end of the new BSD licence text in the COPYRIGHT file.

That being said, I use nvpy daily on my own precious notes database
and it hasn't disappointed me (yet).

Screenshots
===========

This is what nvpy looked like on Windows on May 23, 2012. Search bar at the top showing a regular expression, notes are sorted last modified first, continuously updated markdown preview in chrome behind the nvpy window:

.. image:: https://github.com/cpbotha/nvpy/raw/master/images/nvpy_screenshot_20120523.jpg

Here's a screenshot showing the automatic hyperlinking on Linux:

.. image:: https://github.com/cpbotha/nvpy/raw/master/images/nvpy_linking_screenshot_20120525.png

Installation
============

To install the latest development version from github, do::

    pip install git+https://github.com/cpbotha/nvpy.git#egg=nvpy

OR, to install the version currently on pypi, do::

    pip install nvpy

OR, you can of course use easy\_install instead::

    easy_install nvpy

github always has the latest development version, whereas I upload
tagged snapshots (v0.3 for example) to pypi.

How to run for the first time
=============================

Create a file called .nvpy.cfg in your home directory that looks like
the following::

    [default]
    sn_username = your_simplenote_username
    sn_password = your_simplenote_password

If you installed this via pip install, you should now be able to start
the application by typing "nvpy". The first time you run it, it will take
a while as it downloads all of your simplenote notes. Subsequest runs
are much faster as it uses the database it stores in your home directory.

The `example nvpy.cfg <https://github.com/cpbotha/nvpy/blob/master/nvpy/nvpy-example.cfg>`_ shows how you can configure the font 
family and size.

Features
========

* Syncs with simplenote.
* Partial syncs (whilst notes are being edited) are done by a
  background thread so you can keep on working at light speed.
* Can be used offline, also without simplenote account.
* Search box does realtime regular expression searching in all your
  notes.
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

* Undo / redo.
* Full(ish) screen mode.
* Full syncs also in background thread. At the moment does a full sync
  at startup, which can take a while. nvpy already does background thread
  saving and syncing while you work, so everything you type is backed up
  within a few seconds of you typing it.
* Tag support.

Bugs and feedback
=================

* Report bugs with `the github issue tracker <https://github.com/cpbotha/nvpy/issues>`_.
* It's an even better idea to clone, fix and then send me a pull request.
* If you have questions, or would like to discuss nvpy-related matters, please do so via the `nvpy google discussion group / mailing list <https://groups.google.com/forum/#!forum/nvpy>`_.
* If you really like nvpy, you could make me and you even happier by `tipping me with paypal <https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=BXXTJ9E97DG52>`_! 

Credits
=======

* nvpy uses the `fantastic simplenote.py library by mrtazz <https://github.com/mrtazz/simplenote.py>`_.
* The brilliant application icon, a blue mini car (not as fast as the notational velocity rocket, get it?), is by `Cemagraphics <http://cemagraphics.deviantart.com/>`_.
