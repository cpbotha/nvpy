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
    # these are in reality not hard requirements of nvpy
    install_requires=['Markdown', 'docutils', 'simplenote>=2.0.0'],
    entry_points={
        'gui_scripts': ['nvpy = nvpy.nvpy:main']
    },
    # use MANIFEST.in file
    # because package_data is ignored during sdist
    include_package_data=True,
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: X11 Applications",
        "Environment :: MacOS X",
        "Environment :: Win32 (MS Windows)",
        "Topic :: Utilities",
        "License :: OSI Approved :: BSD License",
    ],
)
