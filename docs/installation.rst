=======================
nvPY installation guide
=======================

There are many (mostly very easy) ways to install nvPY. This document summarises a number of them.

Windows step-by-step for beginners
==================================

1. Download and install (by double-clicking) the Python 2.7.3 Windows Installer: http://python.org/ftp/python/2.7.3/python-2.7.3.msi
2. Download get-pip.py from here: https://raw.github.com/pypa/pip/master/contrib/get-pip.py
3. Double-click the downloaded get-pip.py -- this should install the Python pip installer.
4. Start a command shell by pressing Windows-R and typing "cmd" followed by enter into the input box that appears.
5. At the command shell prompt, type the following::

    \Python27\Scripts\pip install nvpy

6. In c:\\users\\yourlogin\\ create a file called nvpy.cfg, using your favourite text editor, with the lines::

    [nvpy]
    sn_username = your_simplenote_email
    sn_password = your_simplenote_password

7. From now on, start nvpy by double-clicking on "nvpy.exe" in c:\\Python27\\Scripts\\ -- consider creating a shortcut to this on your desktop or in your start menu.

Ubuntu / Mint / Debian step-by-step #1
======================================

On Debian-flavoured systems with apt, this generally works::

    sudo apt-get install python python-tk python-pip
    sudo pip install nvpy

Create a file in your home directory called .nvpy.cfg with just the following contents::

    [nvpy]
    sn_username = your_simplenote_email
    sn_password = your_simplenote_password

To start nvpy, just do::

    nvpy

Advanced users
==============

You can obviously run nvpy directly from a git repo. Start with::

    git clone git://github.com/cpbotha/nvpy.git
    cd nvpy
    python nvpy
    
Don't forget to create .nvpy.cfg in your home directory before you start nvpy.

