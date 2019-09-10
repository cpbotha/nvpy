#!/usr/bin/env python3
# Usage:
#   ./show-all-notes.py

import json
import os
from configparser import ConfigParser

import simplenote

home = os.path.abspath(os.path.expanduser('~'))
cfg_files = [
    # os.path.join(app_dir, 'nvpy.cfg'),
    os.path.join(home, 'nvpy.cfg'),
    os.path.join(home, '.nvpy.cfg'),
    os.path.join(home, '.nvpy'),
    os.path.join(home, '.nvpyrc'),
]

cp = ConfigParser()
cp.read(cfg_files)
user = cp.get('nvpy', 'sn_username', raw=True)
passwd = cp.get('nvpy', 'sn_password', raw=True)

sn = simplenote.Simplenote(user, passwd)
notes, status = sn.get_note_list(data=False)
if status == 0:
    for note in notes:
        note, status = sn.get_note(note['key'])
        if status == 0:
            print(note['key'], json.dumps(note))
        else:
            print(str(note))
else:
    print(str(notes))
