Introduction
============

nvpy is a simplenote-syncing note-taking tool inspired by nvALT and
ResophNotes. It is significantly uglier, but it is cross-platform.

It was written by Charl Botha, who needed a simplenote client on
Linux and doesn't mind ugliness (that much).

DISCLAIMER
----------
If nvpy blows up your computer, loses your job or just deletes all
your notes, I am NOT liable for anything. Also see the liability
clause at the end of the new BSD licence text in the COPYRIGHT file.

That being said, I use nvpy daily on my own precious notes database
and it hasn't disappointed me (yet).

A screenshot
============

This is what nvpy looked like on Windows on May 23, 2012. Search bar at the top showing a regular expression, notes are sorted last modified first, continuously updated markdown preview in chrome behind the nvpy window:

![screenshot](https://github.com/cpbotha/nvpy/raw/master/images/nvpy_screenshot_20120523.jpg)

Installation
============

To get the latest version from github, do:

    pip install git+https://github.com/cpbotha/nvpy.git#egg=nvpy

I'll upload this to pypi soon.

How to run for the first time
=============================

Create a file called .nvpy.cfg in your home directory that looks like
the following:

    [default]
    sn_username = your_simplenote_username
    sn_password = your_simplenote_password

If you installed this via pip install, you should now be able to start
the application by typing "nvpy".


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

Planned features
================

* Automatic hyperlink highlighting in text widget.
* Tag support.
* Full syncs also in background thread. At the moment does a full sync
  at startup, can take a while.

Bugs and feedback
=================

Report bugs with [the github issue tracker](https://github.com/cpbotha/nvpy/issues).

It's an even better idea to clone, fix and then send me a pull
request.

If you really like nvpy, you could make me and you even happier by
[tipping me with
paypal](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=BXXTJ9E97DG52)! 

Credits
=======

* nvpy uses the [fantastic simplenote.py library by mrtazz][snpy]
* The brilliant application icon, a blue mini car (not as fast as the notational velocity rocket, get it?), is by [Cemagraphics][cg]
  
[snpy]: https://github.com/mrtazz/simplenote.py
[cg]: http://cemagraphics.deviantart.com/
