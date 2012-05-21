Introduction
============

nvpy is a simplenote-syncing note-taking tool inspired by nvalt and
resophnotes. It is significantly uglier, but it is cross-platform.

It was written by Charl Botha, who needed a simplenote client on
Linux and doesn't mind ugliness.

How to install
==============

To get the latest version from github, do:

    pip install git+https://github.com/cpbotha/nvpy.git#egg=nvpy

How to run for the first time
=============================

Create a file called .nvpy.cfg in your home directory that looks like
the following:

    [default]
    sn_username = your_simplenote_username
    sn_password = your_simplenote_password

If you installed this via pip install, you should now be able to start
the application app by typing "nvpy".

Features
========

* Syncs with simplenote.
* Partial syncs (whilst notes are being edited) are done by a
  background thread so you can keep on working at light speed.
* Can be used offline, also without simplenote account.
* Search box does realtime regular expression searching in all your
  notes.

Planned features
================

* Markdown rendering to browser.

