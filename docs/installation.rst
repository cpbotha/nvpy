=======================
nvPY installation guide
=======================

There are many (mostly very easy) ways to install nvPY. This document summarises a number of them.

Windows step-by-step for beginners
==================================

Following this recipe, install the nvPY to your computer.

1. Find the latest *stable* release from `the releases page <https://github.com/cpbotha/nvpy/releases>`_.
2. Download :code:`nvpy-windows.zip` file and extract it.
3. Create a setting file.  Start a notepad by pressing Windows-R and typing :code:`notepad %HOMEPATH%\nvpy.cfg`.
   And write the following settings into the notepad. ::

    [nvpy]
    sn_username = your_simplenote_email
    sn_password = your_simplenote_password

4. Start :code:`nvpy.exe`.
5. Wait a little for full synchronization to complete.
6. Consider creating a shortcut to :code:`nvpy.exe` on your desktop or in your start menu.

To upgrade an existing installation of nvpy, just replace the :code:`nvpy` folder with the newer version.


Windows step-by-step for experts
================================

1. Download the Python 3.6 or later.  Don't forget to install `the Python launcher <https://docs.python.org/3.6/using/windows.html#python-launcher-for-windows>`_.
2. Install nvPY from PyPI. ::

    py -3 -m pip install -U nvpy

   OR, download source code from `repository <https://github.com/cpbotha/nvpy>`_, and install it. ::

    git clone https://github.com/cpbotha/nvpy
    cd nvpy
    py -3 -m pip install -U .

3. Create a setting file to :code:`%HOMEPATH%\nvpy.cfg` while referring to `nvpy-example.cfg <https://github.com/cpbotha/nvpy/blob/master/nvpy/nvpy-example.cfg>`_.
4. Start nvPY by pressing Windows-R and typing :code:`nvpy`.

To upgrade an existing installation of nvpy, do the following::

    py -3 -m pip install -U nvpy


Ubuntu / Mint / Debian step-by-step
===================================

On Debian-flavoured systems with apt, current releases of nypy require Python 3.6 or later. If you are running Debian-buster, Ubuntu-bionic, or later, which have a compatible release of Python as the default for `python3`, this generally works::

    sudo apt-get install python3 python3-tk python3-pip
    sudo pip3 install -U nvpy

Older releases may require manual installation of python 3.6 or later.

Create a file in your home directory called :code:`.nvpy.cfg` with just the following contents::

    [nvpy]
    sn_username = your_simplenote_email
    sn_password = your_simplenote_password

To start nvpy, just do::

    nvpy

To upgrade an existing installation of nvpy, do the following::

    sudo pip3 install --upgrade nvpy

Integrating with your Linux desktop environment
-----------------------------------------------

nvPY ships with a `.desktop file <https://github.com/cpbotha/nvpy/blob/master/nvpy/vxlabs-nvpy.desktop>`_, so that you can easily integrate it with your Linux desktop environment. This has been tested on Ubuntu Unity, but should work on KDE, Gnome3 and other environments as well.

First edit the file to check and optionally customize the Exec and Icon entries, then install it with::

    xdg-desktop-menu install vxlabs-nvpy.desktop

Alternative method
==================

Some operating systems will present you with the dependency problems when you install programs using pip without creating a virtual environment. 

One solution is to use `virtualenvwrapper <https://virtualenvwrapper.readthedocs.io/en/latest/index.html>`_.

Another way to install it could be with `Conda or Miniconda <https://conda.io/en/latest/miniconda.html>`_, some distibutions provide conda in their repositories. 

This example shows you how to install Conda on Fedora, standard Bash setup - change it if you use other shell. If your distribution provides the conda package, use your package manager (zypper, pacman etc), otherwise follow the official Conda documentation::

    sudo dnf install conda
    conda init bash
    conda install pip
    conda create -n nvpy
    conda activate nvpy
    pip install nvpy

The resulting installation will end up in :code:`~/.conda/envs/nvpy/bin`. Now symlink it or create an alias for easier access to nvpy binary.

For example NixOS distribution also provides `Conda < https://nixos.org/nixos/packages.html?query=conda>`_, to install::

    nix-env -iA nixos.conda

Then follow the setup above.

Contributors and expert users
=============================

You can install nvPY from a git repository. ::

    git clone git://github.com/cpbotha/nvpy.git
    cd nvpy
    pip3 install -U -e '.[dev]'

Don't forget to create :code:`~/.nvpy.cfg` while referring to `nvpy-example.cfg <https://github.com/cpbotha/nvpy/blob/master/nvpy/nvpy-example.cfg>`_.

To start nvpy, just do::

    nvpy

To browse nvPY internal docs, just do::

    pip3 install -U pdoc3
    pdoc --http localhost:8080 nvpy
    # Open http://localhost:8080, you can see docs.
