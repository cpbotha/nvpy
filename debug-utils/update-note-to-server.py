#!/usr/bin/env python2
# Usage:
#   ./update-note-to-server.py file.json

import json
import os
import sys
import ConfigParser

import simplenote

file_name = sys.argv[1]
new_note = json.loads(open(file_name).read())

home = os.path.abspath(os.path.expanduser('~'))
cfg_files = [
	# os.path.join(app_dir, 'nvpy.cfg'),
	os.path.join(home, 'nvpy.cfg'),
	os.path.join(home, '.nvpy.cfg'),
	os.path.join(home, '.nvpy'),
	os.path.join(home, '.nvpyrc'),
]

cp = ConfigParser.SafeConfigParser()
cp.read(cfg_files)
user = cp.get('nvpy', 'sn_username', raw=True)
passwd = cp.get('nvpy', 'sn_password', raw=True)

sn = simplenote.Simplenote(user, passwd)
note, status = sn.update_note(new_note)
if status == 0:
	print(json.dumps(note))
else:
	print(str(note))
