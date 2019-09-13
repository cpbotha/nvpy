=============
UCS-4 support
=============

The nvPY may not display non-BMP characters such as emoji, some symbols, characters for minor languages, and so on.
The cause is that python and libraries are built without UCS-4 support.

This document provides instructions for resolving this issue.


For Windows
===========

Currently, Python official binary is built without UCS-4 support because it have `some issues <https://bugs.python.org/issue13153>`_.
Therefore, nvPY v2.x.x can not handle non-BMP characters.

The nvPY v1.2.x will be able to handle non-BMP characters.  It's not a recommended way, but it works well.


For Linux
=========

Try to rebuild the python3, tk, and tcl with :code:`CFLAGS=-DTCL_UTF_MAX=6` and :code:`--enable-unicode=ucs4` option.
Note that current version tcl/tk is not fully support unicode.  This solution is not perfect, but displayable characters will be increase.

1. Download source codes of `python3 <https://www.python.org/downloads/source/>`_, `tk, and tcl <https://www.tcl.tk/software/tcltk/download.html>`_.
2. Build and install as following. ::

    # build.sh
    export CFLAGS=-DTCL_UTF_MAX=6
    export PREFIX=/opt/nvpy
    export LD_LIBRARY_PATH=$PREFIX/lib

    tar xf tcl8.6.9-src.tar.gz
    tar xf tk8.6.9-src.tar.gz
    tar xf Python-3.7.4.tgz

    sudo apt build-dep -y tcl tk python3.7

    cd tcl8.6.9/unix
    ./configure --enable-threads --enable-shared --enable-symbols --enable-64bit --enable-langinfo --enable-man-symlinks
    make
    sudo make install
    cd ../..

    cd tk8.6.9/unix
    ./configure --enable-threads --enable-shared --enable-symbols --enable-64bit --enable-man-symlinks
    make
    sudo make install
    cd ../..

    cd Python-3.7.4
    ./configure --enable-shared --enable-optimizations --enable-ipv6 --enable-unicode=ucs4 --with-lto --with-signal-module --with-pth --with-wctype-functions --with-tcltk-includes=/usr/local/include/ --with-tcltk-libs=/usr/local/lib/
    make
    sudo make install

3. Copy-and-paste some emoji to nvPY.  If it can be displayed normally, it is successful.
   You can easily copy emoji from `getemoji.com <https://getemoji.com>`_.
