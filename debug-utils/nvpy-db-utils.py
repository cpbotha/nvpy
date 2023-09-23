#!/usr/bin/env python3
# Usage:
#   # Validate local nvPY database.
#   ./nvpy-db-utils.py validate
#
#   # Clear local and remote database.
#   # WARNING: ALL NOTES WILL BE DELETED WITHOUT ANY PROMPT.
#   ./nvpy-db-utils.py delete --remote --all
#   ./nvpy-db-utils.py delete --local --all
#
#   # Download all notes to local.
#   ./nvpy-db-utils.py update --direction download --all
#
#   # Use custom configuration.
#   ./nvpy-db-utils.py --cfg ~/nvpy-backup.cfg update --direction download --all

import json
import traceback
import time
import pathlib
import argparse
import typing

import simplenote  # type:ignore

from nvpy import nvpy


class APIError(Exception):
    pass


class LocalDB:

    def __init__(self, db_path):
        self.db_path = pathlib.Path(db_path)

    def target(self, keys: typing.Iterable[str], is_all: bool) -> typing.Iterable[str]:
        files = self.target_files(keys, is_all=is_all)
        return (self.key_from_path(p) for p in files)

    def target_files(self, keys: typing.Iterable[str], is_all: bool) -> typing.Iterable[pathlib.Path]:
        if is_all:
            # The keys parameter ignores.
            return self.db_path.glob('*.json')
        else:
            return (self.path_from_key(k) for k in keys)

    def key_from_path(self, path: pathlib.Path) -> str:
        return path.with_suffix('').name

    def path_from_key(self, key) -> pathlib.Path:
        return self.db_path / f'{key}.json'

    def update(self, key, note):
        data = json.dumps(note)
        self.path_from_key(key).write_text(data)


class RemoteDB:

    def __init__(self, user, password):
        self.sn = simplenote.Simplenote(user, password)
        self.sn.get_token()

    def targets(self, keys: typing.Iterable[str], is_all: bool) -> typing.Iterable[str]:
        if is_all:
            # The keys parameter ignores.
            notes, status = self.sn.get_note_list(data=False)
            if status != 0:
                # error
                raise APIError(notes)
            keys = (n['key'] for n in notes)
        return keys

    def delete(self, key):
        print('delete', key)
        res, status = self.sn.delete_note(key)
        if status != 0:
            raise APIError(res)

    def get(self, key) -> dict:
        print('get', key)
        note, status = self.sn.get_note(key)
        if status != 0:
            raise APIError(note)
        return note

    def update(self, key: str, note: dict):
        print('update', key)
        note, status = self.sn.update_note(note)
        if status != 0:
            raise APIError(note)


class ValidateCmd:

    def run(self, args, config):
        files = LocalDB(config.db_path).target_files(args.keys, is_all=not args.keys)
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
            return 0
        else:
            print('Done.  Some notes are broken :-(')
            print('See above log for details.')
            return 1


class DeleteCmd:

    def run(self, args, config):
        if args.local:
            local = LocalDB(config.db_path)
            for t in local.target_files(args.keys, is_all=args.all):
                t.unlink(missing_ok=True)
        if args.remote:
            r = RemoteDB(config.sn_username, config.sn_password)
            for t in r.targets(args.keys, is_all=args.all):
                r.delete(t)


class UpdateCmd:

    def run(self, args, config):
        remote = RemoteDB(config.sn_username, config.sn_password)
        local = LocalDB(config.db_path)
        if args.direction == 'download':
            for key in remote.targets(args.keys, is_all=args.all):
                note = remote.get(key)
                local.update(key, note)
        elif args.direction == 'upload':
            for key in local.target(args.keys, is_all=args.all):
                data = local.path_from_key(key).read_text()
                note = json.loads(data)
                remote.update(key, note)
        else:
            raise RuntimeError('bug: invalid direction', args.direction)


def parse_cmd_line_args():
    p = argparse.ArgumentParser()
    p.add_argument('--cfg', '-c', dest='cfg', type=pathlib.Path, metavar='nvpy.cfg', help='path to config file')
    sp = p.add_subparsers(required=True)

    validate = sp.add_parser('validate')
    validate.set_defaults(clazz=ValidateCmd)
    validate.add_argument('keys', nargs='*')

    delete = sp.add_parser('delete')
    delete.set_defaults(clazz=DeleteCmd)
    delete.add_argument('--all', '-a', action='store_true')
    delete.add_argument('--local', '-l', action='store_true')
    delete.add_argument('--remote', '-r', action='store_true')
    delete.add_argument('keys', nargs='*')

    update = sp.add_parser('update')
    update.set_defaults(clazz=UpdateCmd)
    update.add_argument('--all', '-a', action='store_true')
    update.add_argument('--direction', '-d', choices=('download', 'upload'), required=True)
    update.add_argument('keys', nargs='*')

    return p.parse_args()


def main():
    args = parse_cmd_line_args()
    cfg_files = None
    if args.ns:
        cfg_files = [args.cfg]
    config = nvpy.Config(nvpy.get_appdir(), cfg_files)
    return args.clazz().run(args, config)


if __name__ == '__main__':
    exit(main())
