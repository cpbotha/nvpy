=============
UCS-4 support
=============

The nvPY may not display non-BMP characters such as emoji, some symbols, characters for minor languages, and so on.
The cause is that python and libraries are built without UCS-4 support.

This document provides instructions for resolving this issue.

For Windows
===========

1. Get python2 installer from `python official site <https://python.org>`_.
2. Install it.
3. Reinstall nvpy. ::

    python2 -m pip install -u nvpy

4. Copy-and-paste some emoji to nvPY.  If it can be displayed normally, it is successful.
   You can easily copy emoji from `getemoji.com <https://getemoji.com>`_.

For Linux
=========

Rebuild the python2, tk, and tcl with :code:`CFLAGS=-DTCL_UTF_MAX=6` and :code:`--enable-unicode=ucs4` option.

1. Download the source codes of `python2 <https://github.com/python/cpython/tree/2.7>`_, `tk, and tcl <https://www.tcl.tk/software/tcltk/download.html>`_.
2. Build and install as following. ::

    # build.sh
    export CFLAGS=-DTCL_UTF_MAX=6

    tar xf tcl8.6.9-src.tar.gz
    tar xf tk8.6.9-src.tar.gz
    git clone https://github.com/python/cpython

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

    cd cpython
    git checkout -b 2.7 remotes/origin/2.7
    ./configure --enable-shared --enable-optimizations --enable-ipv6 --enable-unicode=ucs4 --with-lto --with-signal-module --with-pth --with-wctype-functions --with-tcltk-includes=/usr/local/include/ --with-tcltk-libs=/usr/local/lib/
    make
    sudo make install

3. Copy-and-paste some emoji to nvPY.  If it can be displayed normally, it is successful.
   You can easily copy emoji from `getemoji.com <https://getemoji.com>`_.
