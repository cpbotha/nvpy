#!/usr/bin/env python3
import json
import os
import glob
import traceback
import time

cache_dir = os.path.expanduser('~/.nvpy')
files = glob.glob(cache_dir + '/*.json')

now = time.time()
is_valid = True
for file in files:
    with open(file) as f:
        obj = json.load(f)
        try:
            # See https://simplenotepy.readthedocs.io/en/latest/api.html#simperium-api-note-object

            # Optional field for simplenote.
            # Only if we have synced with simplenote once or more times, those fields may exist.
            # TODO: New note format does not require the key field. Please consider removing it.
            if 'key' in obj:
                assert type(obj['key']) == str
            if 'deleted' in obj:
                assert type(obj['deleted']) in [bool, int]
            if 'version' in obj:
                assert type(obj['version']) == int
            if 'systemtags' in obj:
                assert type(obj['systemtags']) == list
            if 'sharedURL' in obj:
                assert type(obj['sharedURL']) == str
            if 'publishURL' in obj:
                assert type(obj['publishURL']) == str

            # Required fields for simplenote.
            assert 'modifydate' in obj and type(obj['modifydate']) in [float, int] and obj['modifydate'] <= now
            assert 'createdate' in obj and type(obj['createdate']) in [float, int] and obj['createdate'] <= now
            assert 'tags' in obj and type(obj['tags']) == list
            assert 'content' in obj and type(obj['content']) == str

            # Optional field for nvpy.
            if 'savedate' in obj:
                assert type(obj['savedate'] in [float, int])
                assert float(obj['savedate']) <= now
            # Required field for nvpy.
            assert 'syncdate' in obj and type(obj['syncdate'] in [float, int]) and obj['createdate'] <= now
        except:
            print('{}  Invalid'.format(file))
            print(obj)
            print(traceback.format_exc())
            print('')
            is_valid = False
        else:
            print('{}  OK'.format(file))

if is_valid:
    print('Done.  All notes are valid!')
else:
    print('Done.  Some notes are broken :-(')
    print('See above log for details.')
    exit(1)
