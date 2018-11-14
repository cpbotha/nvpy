#!/usr/bin/env python2
import json
import os
import glob

cache_dir = os.path.expanduser('~/.nvpy')
files = glob.glob(cache_dir + '/*.json')

for file in files:
	with open(file) as f:
		obj = json.load(f)
		try:
			# See https://simplenotepy.readthedocs.io/en/latest/api.html#simperium-api-note-object
			assert 'key' in obj        and type(obj['key']) == unicode
			assert 'deleted' in obj    and type(obj['deleted']) in [bool, int]
			assert 'modifydate' in obj and type(obj['modifydate']) in [float, int]
			assert 'createdate' in obj and type(obj['createdate']) in [float, int]
			assert 'version' in obj    and type(obj['version']) == int
			assert 'systemtags' in obj and type(obj['systemtags']) == list
			assert 'tags' in obj       and type(obj['tags']) == list
			assert 'content' in obj    and type(obj['content']) == unicode
			# nvpy required fields.
			assert 'savedate' in obj   and type(obj['savedate'] in [float, int])
			assert 'syncdate' in obj   and type(obj['syncdate'] in [float, int])
		except:
			print('{}  Invalid'.format(file))
			print(obj)
			raise
		else:
			print('{}  OK'.format(file))

print('Done.  All notes are valid!')

