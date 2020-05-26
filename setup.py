#!/usr/bin/env python3

import os
from setuptools import setup
import nvpy


# Utility function to read the README file.
# Used for the long_description.  It's nice, because now 1) we have a top level
# README file and 2) it's easier to type in the README file than to put a raw
# string in below ...
def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


setup(
    name="nvpy",
    version=nvpy.VERSION,
    author="Charl P. Botha",
    author_email="cpbotha@vxlabs.com",
    description="A cross-platform simplenote-syncing note-taking app inspired by Notational Velocity.",
    license="BSD",
    keywords="simplenote note-taking tkinter nvalt markdown",
    url="https://github.com/cpbotha/nvpy",
    packages=['nvpy'],
    long_description=read('README.rst'),
    install_requires=[
        # These are in reality not hard requirements of nvpy.  If these packages are not installed,
        # the Markdown/reStructuredText rendering feature will not work.  But basic functions should work.
        'Markdown',
        'docutils',
        # This is hard requirements of nvpy.
        'simplenote>=2.1.4',
    ],
    extras_require={
        # development and test requirements.
        'dev': ['mock', 'yapf', 'pdoc3', 'nose', 'nose-timer', 'mypy'],
    },
    entry_points={'gui_scripts': ['nvpy = nvpy.nvpy:main']},
    # use MANIFEST.in file
    # because package_data is ignored during sdist
    include_package_data=True,
    classifiers=[
        # See https://pypi.org/classifiers/
        "Development Status :: 5 - Production/Stable",
        "Environment :: X11 Applications",
        "Environment :: MacOS X",
        "Environment :: Win32 (MS Windows)",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Topic :: Utilities",
        "License :: OSI Approved :: BSD License",
    ],
)
