#!/usr/bin/env python3
# Usage:
#   ./get-note-from-server.py note_id

import json
import os
import sys
from configparser import ConfigParser

import simplenote

note_id = sys.argv[1]

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
note, status = sn.get_note(note_id)
if status == 0:
    print(json.dumps(note))
else:
    print(str(note))
