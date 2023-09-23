import itertools
import logging
import math
import typing
import time
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

from nvpy.notes_db import WriteError, UpdateResult, Note, NotesDB
from ._mixin import DBMixin


class timeout:

    def __init__(self, seconds):
        self.seconds = seconds

    def __enter__(self):
        self.die_after = time.time() + self.seconds
        return self

    def __exit__(self, type, value, traceback):
        pass

    @property
    def timed_out(self) -> bool:
        return time.time() > self.die_after


class SaveToJson(DBMixin, unittest.TestCase):

    def test_database_must_write_json_file(self):
        db = self._db()
        rk = 'remote_key'
        lk = 'local_key'
        fname = f'{lk}.json'

        # Must create json file.
        note = {
            'key': rk,
            'content': 'foo',
        }
        db.helper_save_note(lk, note)
        self.assertEqual(set(self._json_files()), {fname})

        # Must delete json file if the note is marked as deleted.
        note = {
            'deleted': True,
        }
        db.helper_save_note(lk, note)
        self.assertEqual(set(self._json_files()), set())

    @patch('pathlib.Path.write_text', side_effect=IOError('no space left on device'))
    def test_database_must_handle_write_error(self, write_text: MagicMock):
        db = self._db()
        lk = 'local_key'
        note = {'content': 'foo'}

        with self.assertRaises(WriteError):
            db.helper_save_note(lk, note)
        self.assertTrue(write_text.called)


class SaveToText(DBMixin, unittest.TestCase):

    def test_database_must_write_text_file(self):
        db = self._db(notes_as_txt=True)
        lk = 'local_key'
        fname = 'example note.txt'
        renamed_fname1 = 'title is modified.txt'
        renamed_fname2 = 'text file is renamed.txt'

        # Must create text file.
        note = {'content': 'example note'}
        db.helper_save_note(lk, note)
        self.assertEqual(set(self._text_files()), {fname})

        # Must rename file if title is modified.
        note = {'content': 'title is modified'}
        db.helper_save_note(lk, note)
        self.assertEqual(set(self._text_files()), {renamed_fname1})

        # Ignore error if a text file is renamed/deleted by other software.
        note = {'content': 'text file is renamed'}
        (Path(db.config.txt_path) / renamed_fname1).unlink()
        db.helper_save_note(lk, note)
        self.assertEqual(set(self._text_files()), {renamed_fname2})

        # Must delete file if the note is marked as deleted.
        note = {'content': 'deleted note', 'deleted': True}
        db.helper_save_note(lk, note)
        self.assertEqual(set(self._text_files()), set())

    @patch('pathlib.Path.write_text', side_effect=IOError('no space left on device'))
    def test_database_must_handle_write_error(self, write_text: MagicMock):
        db = self._db(notes_as_txt=True)
        lk = 'local_key'
        note = {'content': 'example note'}

        with self.assertRaises(WriteError):
            db.helper_save_note(lk, note)
        self.assertTrue(write_text.called)


class PatchedDBMixin(DBMixin):
    __MUST_NOT_CALL = RuntimeError('must not call')

    def _patched_db(self,
                    notes_as_txt: bool = False,
                    se_update_note: typing.Any = __MUST_NOT_CALL,
                    se_get_note: typing.Any = __MUST_NOT_CALL,
                    se_get_note_list: typing.Any = __MUST_NOT_CALL,
                    se_update_note_to_server: typing.Any = None):
        """ Get patched NotesDB object.

        :param notes_as_txt: Enable or disable notes_as_txt feature
        :param se_update_note: side effect of update_note()
        :param se_get_note: side effect of get_note()
        :param se_get_note_list: side effect of get_note_list()
        :return:
        """
        db = self._db(notes_as_txt=notes_as_txt, simplenote_sync=True)
        db.simplenote = MagicMock()
        db.simplenote.update_note.side_effect = se_update_note
        db.simplenote.get_note.side_effect = se_get_note
        db.simplenote.get_note_list.side_effect = se_get_note_list
        if se_update_note_to_server is not None:
            db.update_note_to_server = MagicMock()
            db.update_note_to_server.side_effect = se_update_note_to_server
        db.notify_observers = MagicMock()
        db.notify_observers.side_effect = lambda *args: logging.info(str(args))
        return db

    def _wait_worker(self, db: NotesDB):
        timeout = 1
        loop_interval = 0.1
        max_loop_count = math.ceil(timeout / loop_interval)
        for _ in range(max_loop_count):
            if not db.is_worker_busy():
                return
            time.sleep(0.1)
        raise TimeoutError('NotesDB workers still busy')


class UpdateNoteToServer(PatchedDBMixin, unittest.TestCase):
    """ Test class for the NotesDB.update_note_to_server() method.

    Test Case Matrix:
                     success
                     |  fail_1
                     |  |  failure_recovery_1
                     |  |  |  fail_2
                     |  |  |  |  fail_3
                     |  |  |  |  |
    update_note      o  x  x  x  x
    has key          -  o  o  o  x
    get_note         -  o  o  x  -
    remote != local  -  o  x  -  -
    """

    def test_success(self):
        old_note = {'key': 'remote_key', 'content': 'foo'}
        new_note = {'key': 'remote_key', 'content': 'foo bar'}
        note = old_note.copy()

        db = self._patched_db(
            se_update_note=((new_note.copy(), 0), ),
            se_get_note=((RuntimeError('must not call'), 1), ),
        )
        result = db.update_note_to_server(note)
        self.assertEqual(result, UpdateResult(note=new_note, is_updated=True, error_object=None))
        self.assertEqual(note, old_note)

    def test_fail_1(self):
        local_note = {'key': 'remote_key', 'content': 'foo', 'savedate': 2, 'syncdate': 5}
        remote_note = {'key': 'remote_key', 'content': 'bar'}
        note = local_note.copy()
        update_err = OSError('connection refused')

        db = self._patched_db(
            se_update_note=((update_err, 1), ),
            se_get_note=((remote_note, 0), ),
        )
        result = db.update_note_to_server(note)
        self.assertEqual(result, UpdateResult(note=None, is_updated=False, error_object=update_err))
        self.assertEqual(note, local_note)

    def test_failure_recovery_1(self):
        local_note = {'key': 'remote_key', 'content': 'foo', 'savedate': 2, 'syncdate': 5}
        remote_note = {'key': 'remote_key', 'content': 'foo'}
        note = local_note.copy()
        update_err = OSError('400 bad request')

        db = self._patched_db(
            se_update_note=((update_err, 1), ),
            se_get_note=((remote_note, 0), ),
        )
        result = db.update_note_to_server(note)
        self.assertEqual(result, UpdateResult(note=local_note, is_updated=False, error_object=None))
        self.assertEqual(note, local_note)

    def test_fail_2(self):
        local_note = {'key': 'remote_key', 'content': 'foo', 'savedate': 2, 'syncdate': 5}
        note = local_note.copy()
        update_err = OSError('400 bad request')
        get_err = OSError('connection refused')

        db = self._patched_db(
            se_update_note=((update_err, 1), ),
            se_get_note=((get_err, 1), ),
        )
        result = db.update_note_to_server(note)
        self.assertEqual(
            result,
            UpdateResult(note=None, is_updated=False, error_object={
                'update_error': update_err,
                'get_error': get_err
            }))
        self.assertEqual(note, local_note)

    def test_fail_3(self):
        local_note = {'content': 'foo', 'savedate': 2, 'syncdate': 5}
        note = local_note.copy()
        update_err = OSError('connection refused')

        db = self._patched_db(
            se_update_note=((update_err, 1), ),
            se_get_note=((RuntimeError('must not call'), 1), ),
        )
        result = db.update_note_to_server(note)
        self.assertEqual(result, UpdateResult(
            note=None,
            is_updated=False,
            error_object=update_err,
        ))
        self.assertEqual(note, local_note)


class SyncNoteUnthreaded(PatchedDBMixin, unittest.TestCase):
    """
    Test Case Matrix for the NotesDB.sync_note_unthreaded():
                                      update_1
                                      |  fail_1
                                      |  |  update_2
                                      |  |  |  no_update
                                      |  |  |  |  fail_2
                                      |  |  |  |  |
    need sync to server               o  o  x  x  x
    update_note_to_server             o  x  -  -  -
    get_note                          -  -  o  o  x
    remote note is newer than local   -  -  o  x  -
    """

    def test_update_1(self):
        key = 'KEY'
        local_note = {
            'key': key,
            'content': 'this note is latest',
            'modifydate': 2,
            'savedate': 3,
            'syncdate': 1,
        }
        updated_remote_note = {
            'key': key,
            'content': 'merged by remote',
            'modifydate': 90,
        }
        expected_note = {
            'key': key,
            'content': 'merged by remote',
            'modifydate': 90,
            'savedate': 3,
            'syncdate': 99,
        }
        db = self._patched_db(se_update_note=((updated_remote_note, 0), ))
        db.notes = {
            key: local_note,
        }
        with patch('time.time', side_effect=itertools.repeat(99)):
            result = db.sync_note_unthreaded(key)
        self.assertEqual(result, (key, True))
        self.assertEqual(db.notes, {
            key: expected_note,
        })

    def test_fail_1(self):
        key = 'KEY'
        local_note = {
            'key': key,
            'content': 'this note is latest',
            'modifydate': 2,
            'savedate': 3,
            'syncdate': 1,
        }
        update_result = UpdateResult(
            note=None,
            is_updated=False,
            error_object=OSError('connection refused'),
        )
        db = self._patched_db(se_update_note_to_server=(update_result, ))
        db.notes = {
            key: local_note.copy(),
        }
        result = db.sync_note_unthreaded(key)
        self.assertIsNone(result)
        self.assertEqual(db.notes, {
            key: local_note,
        })

    def test_update_2(self):
        key = 'KEY'
        local_note = {
            'key': key,
            'content': 'this note is old',
            'modifydate': 1,
            'savedate': 2,
            'syncdate': 3,
        }
        remote_note = {
            'key': key,
            'content': 'this note is latest',
            'modifydate': 90,
        }
        expected_note = {
            'key': key,
            'content': 'this note is latest',
            'modifydate': 90,
            'savedate': 2,
            'syncdate': 99,
        }
        db = self._patched_db(se_get_note=((remote_note, 0), ))
        db.notes = {
            key: local_note.copy(),
        }
        with patch('time.time', side_effect=itertools.repeat(99)):
            result = db.sync_note_unthreaded(key)
        self.assertEqual(result, (key, True))
        self.assertEqual(db.notes, {
            key: expected_note,
        })

    def test_no_update(self):
        key = 'KEY'
        local_note = {
            'key': key,
            'content': 'this note is old',
            'modifydate': 1,
            'savedate': 2,
            'syncdate': 3,
        }
        remote_note = {
            'key': key,
            'content': 'this note is latest',
            'modifydate': 1,
        }
        expected_note = local_note
        db = self._patched_db(se_get_note=((remote_note, 0), ))
        db.notes = {
            key: local_note.copy(),
        }
        result = db.sync_note_unthreaded(key)
        self.assertEqual(result, (key, False))
        self.assertEqual(db.notes, {
            key: expected_note,
        })

    def test_fail_2(self):
        key = 'KEY'
        local_note = {
            'key': key,
            'content': 'this note is old',
            'modifydate': 1,
            'savedate': 2,
            'syncdate': 3,
        }
        get_note_err = OSError('connection refused')
        expected_note = local_note
        db = self._patched_db(se_get_note=((get_note_err, 1), ))
        db.notes = {
            key: local_note.copy(),
        }
        result = db.sync_note_unthreaded(key)
        self.assertIsNone(result)
        self.assertEqual(db.notes, {
            key: expected_note,
        })


class SyncFullUnthreaded(PatchedDBMixin, unittest.TestCase):
    """
    Test Case Matrix for step 1:
                              change_local_key
                              |  update
                              |  |  fail
                              |  |  |  skip
                              |  |  |  |
    has local changed notes   o  o  o  x
    update_note_to_server     o  o  x  -
    key is changed            o  x  -  -

    Test Case Matrix for step 2:
                    success
                    |  fail
                    |  |
    get_note_list   o  x

    Test Case Matrix for step 3:
                              new_note
                              |  delete_1
                              |  |  delete_2 (skip)
                              |  |  |  skip
                              |  |  |  |
    found a local only note   o  o  o  x
    note is not synced        o  x  x  -
    notes_as_text             -  o  x  -

    Test Case Matrix for step 4:
                              skip
                              |  update_local_1 (skip)
                              |  |  update_local_2
                              |  |  |  fail_1
                              |  |  |  |  new_note_1 (skip)
                              |  |  |  |  |  new_note_2
                              |  |  |  |  |  |  fail_2
                              |  |  |  |  |  |  |
    note exists in local      o  o  o  o  x  x  x
    local note is latest      o  x  x  x  -  -  -
    has content in response   -  o  x  x  o  x  x
    get_note                  -  -  o  x  -  o  x

    Test Case Matrix for step 5:
    (omitted)
    """

    def test_step1_change_local_key(self):
        local_note = {'key': 'local_id', 'content': 'created by local', 'modifydate': 2, 'savedate': 3, 'syncdate': 1}
        remote_note = {'key': 'remote_id', 'content': 'modified', 'modifydate': 3}
        merged_note = {'key': 'remote_id', 'content': 'modified', 'modifydate': 3, 'savedate': 4, 'syncdate': 4}
        db = self._patched_db(se_update_note=((remote_note.copy(), 0), ))
        db.notes['local_id'] = local_note.copy()
        self.assertTrue(Note(local_note).need_sync_to_server)
        with patch('time.time', side_effect=itertools.repeat(4)):
            db.sync_full_unthreaded()
        self.assertEqual(db.notes, {'remote_id': merged_note.copy()})
        self.assertEqual(set(self._json_files()), {'remote_id.json'})

    def test_step1_update(self):
        local_note = {'key': 'id', 'content': 'created by local', 'modifydate': 2, 'savedate': 3, 'syncdate': 1}
        remote_note = {'key': 'id', 'content': 'modified', 'modifydate': 3}
        merged_note = {'key': 'id', 'content': 'modified', 'modifydate': 3, 'savedate': 4, 'syncdate': 4}
        db = self._patched_db(se_update_note=((remote_note.copy(), 0), ))
        db.notes['id'] = local_note.copy()
        self.assertTrue(Note(local_note).need_sync_to_server)
        with patch('time.time', side_effect=itertools.repeat(4)):
            db.sync_full_unthreaded()
        self.assertEqual(db.notes, {'id': merged_note.copy()})
        self.assertEqual(set(self._json_files()), {'id.json'})

    def test_step1_fail(self):
        local_note = {'key': 'id', 'content': 'created by local', 'modifydate': 2, 'savedate': 3, 'syncdate': 1}
        error = OSError('connection refused')
        db = self._patched_db(se_update_note=((error, 1), ), se_get_note=((error, 1), ))
        db.notes['id'] = local_note.copy()
        self.assertTrue(Note(local_note).need_sync_to_server)
        with patch('time.time', side_effect=itertools.repeat(4)):
            with self.assertLogs() as logs:
                db.sync_full_unthreaded()
        self.assertEqual(db.notes, {'id': local_note.copy()})
        self.assertIn('Sync step 1 error - Could not update note id to server: ', '\n'.join(logs.output))

    def test_step2_fail(self):
        error = OSError('connection refused')
        db = self._patched_db(se_get_note_list=((error, 1), ))
        with self.assertLogs() as logs:
            db.sync_full_unthreaded()
        self.assertIn('Could not get note list from server: connection refused', '\n'.join(logs.output))

    def test_step3_new_note(self):
        new_note = {
            'key': 'new_note',
            'content': 'this note created during full sync',
            'syncdate': 0,
        }
        local_notes = {}
        server_notes = {}

        def add_note_to_local_notes(*args, **kwargs):
            local_notes[new_note['key']] = new_note
            return server_notes, 0

        db = self._patched_db(se_get_note_list=add_note_to_local_notes)
        db.notes = local_notes
        db.sync_full_unthreaded()
        self.assertEqual(db.notes, {new_note['key']: new_note})

    def test_step3_delete_1(self):
        local_only_note = {
            'key': 'note',
            'content': 'this note deleted by remote',
            'modifydate': 1,
            'savedate': 2,
            'syncdate': 3,
        }
        local_notes = {
            local_only_note['key']: local_only_note,
        }
        remote_notes = {}
        db = self._patched_db(notes_as_txt=True, se_get_note_list=((remote_notes, 0), ))
        db.notes = local_notes
        with self.assertLogs() as logs:
            db.sync_full_unthreaded()
        self.assertIn('Deleted note 1.', '\n'.join(logs.output))

    def test_step4_update_local_2(self):
        old_note = {
            'key': 'KEY',
            'content': 'old note',
            'modifydate': 1,
            'savedate': 2,
            'syncdate': 3,
        }
        new_note = {
            'key': 'KEY',
            'content': 'new note',
            'modifydate': 11,
        }
        local_notes = {
            old_note['key']: old_note,
        }
        remote_notes = [
            {
                'key': 'KEY',
                'modifydate': 11
            },
        ]
        db = self._patched_db(se_get_note_list=((remote_notes, 0), ), se_get_note=((new_note, 0), ))
        db.notes = local_notes
        with self.assertLogs() as logs:
            with patch('time.time', side_effect=itertools.repeat(33)):
                db.sync_full_unthreaded()
        self.assertEqual(db.notes, {
            'KEY': {
                'key': 'KEY',
                'content': 'new note',
                'modifydate': 11,
                'savedate': 33,
                'syncdate': 33,
            },
        })
        self.assertIn('Synced newer note 0 (1) from server.', '\n'.join(logs.output))

    def test_step4_fail_1(self):
        old_note = {
            'key': 'KEY',
            'content': 'old note',
            'modifydate': 1,
            'savedate': 2,
            'syncdate': 3,
        }
        error = OSError('connection refused')
        local_notes = {
            old_note['key']: old_note,
        }
        remote_notes = [
            {
                'key': 'KEY',
                'modifydate': 11
            },
        ]
        db = self._patched_db(se_get_note_list=((remote_notes, 0), ), se_get_note=((error, 1), ))
        db.notes = local_notes
        with self.assertLogs() as logs:
            with patch('time.time', side_effect=itertools.repeat(33)):
                db.sync_full_unthreaded()
        self.assertEqual(db.notes, {
            'KEY': {
                'key': 'KEY',
                'content': 'old note',
                'modifydate': 1,
                'savedate': 2,
                'syncdate': 3,
            },
        })
        self.assertIn('Error syncing newer note KEY from server: connection refused', '\n'.join(logs.output))

    def test_step4_new_note_2(self):
        new_note = {
            'key': 'KEY',
            'content': 'new note',
            'modifydate': 11,
        }
        local_notes = {}
        remote_notes = [
            {
                'key': 'KEY',
                'modifydate': 11
            },
        ]
        db = self._patched_db(se_get_note_list=((remote_notes, 0), ), se_get_note=((new_note, 0), ))
        db.notes = local_notes
        with self.assertLogs() as logs:
            with patch('time.time', side_effect=itertools.repeat(33)):
                db.sync_full_unthreaded()
        self.assertEqual(db.notes, {
            'KEY': {
                'key': 'KEY',
                'content': 'new note',
                'modifydate': 11,
                'savedate': 33,
                'syncdate': 33,
            },
        })
        self.assertIn('Synced new note 0 (1) from server.', '\n'.join(logs.output))

    def test_step4_fail_2(self):
        error = OSError('connection refused')
        local_notes = {}
        remote_notes = [
            {
                'key': 'KEY',
                'modifydate': 11
            },
        ]
        db = self._patched_db(se_get_note_list=((remote_notes, 0), ), se_get_note=((error, 1), ))
        db.notes = local_notes
        with self.assertLogs() as logs:
            with patch('time.time', side_effect=itertools.repeat(33)):
                db.sync_full_unthreaded()
        self.assertEqual(db.notes, {})
        self.assertIn('Error syncing new note KEY from server: connection refused', '\n'.join(logs.output))


class SaveThreaded(PatchedDBMixin, unittest.TestCase):
    NOTE = {
        'key': 'a',
        'content': 'modified note',
        'modifydate': 3,
        'savedate': 1,
        'syncdate': 3,
    }
    NOTE_MODIFIED = {
        'key': 'a',
        'content': 'modified note',
        'modifydate': 3,
        'savedate': 99,
        'syncdate': 3,
    }

    def test_save_a_note(self):
        db = self._patched_db()
        db.notes = {
            'a': self.NOTE.copy(),
        }
        self.assertTrue(Note(db.notes['a']).need_save)
        with patch('time.time', side_effect=itertools.repeat(99)):
            n1 = db.save_threaded()
            self.assertEqual(n1, 0)
            # Wait for a note to be saved.
            self._wait_worker(db)
        self.assertFalse(db.is_worker_busy())
        with self.assertLogs() as logs:
            n2 = db.save_threaded()
        self.assertEqual(n2, 1)

        self.assertEqual(db.notes, {
            'a': self.NOTE_MODIFIED.copy(),
        })
        self.assertIn("NoteStatusChangedEvent(what='savedate', key='a')", '\n'.join(logs.output))

    def test_save_error(self):
        # os._exit にパッチを当てられないため、このテストケースは実装しない。
        pass


class SyncThreaded(PatchedDBMixin, unittest.TestCase):
    """
    Test cases for the sync_to_server_threaded() and worker_sync().

                                         changed
                                         |  no_changed
                                         |  |  error
                                         |  |  |  new_note
                                         |  |  |  |  skip sync
                                         |  |  |  |  |
    task.key in threaded_syncing_keys    o  o  o  o  x
    note has a key                       o  o  o  x  -
    update_note_to_server() is succeed   o  o  x  -  -
    result.is_updated                    o  x  -  -  -
    remote_note has 'content'            o  -  -  -  -
    """
    NOTE = {
        'key': 'a',
        'content': 'example note',
        'modifydate': 2,
        'savedate': 3,
        'syncdate': 1,
    }
    REMOTE_NOTE = {
        'key': 'a',
        'content': 'modified note',
        'modifydate': 2,
    }
    NOTE_MODIFIED = {
        'key': 'a',
        'content': 'modified note',
        'modifydate': 2,
        'savedate': 3,
        'syncdate': 99,
    }
    NEW_LOCAL_NOTE = {
        'content': 'modified note',
        'modifydate': 2,
        'savedate': 0,
        'syncdate': 0,
    }
    SYNCED_NOTE = {
        'key': 'a',
        'content': 'example note',
        'modifydate': 2,
        'savedate': 3,
        'syncdate': 4,
    }

    def test_changed(self):
        with patch('time.time', side_effect=itertools.repeat(99)):
            result = UpdateResult(
                note=self.REMOTE_NOTE.copy(),
                is_updated=True,
                error_object=None,
            )
            db = self._patched_db(se_update_note_to_server=[result])
            db.notes = {
                'a': self.NOTE.copy(),
            }
            n1 = db.sync_to_server_threaded(wait_for_idle=False)
            self.assertEqual(n1, (0, 0))
            self._wait_worker(db)
            n2 = db.sync_to_server_threaded(wait_for_idle=False)
            self.assertEqual(n2, (1, 0))
            self.assertFalse(db.is_worker_busy())
            self.assertEqual(db.notes, {
                'a': self.NOTE_MODIFIED.copy(),
            })

    def test_no_changed(self):
        result = UpdateResult(
            note=self.NOTE_MODIFIED.copy(),
            is_updated=False,
            error_object=None,
        )
        db = self._patched_db(se_update_note_to_server=[result])
        db.notes = {
            'a': self.NOTE_MODIFIED.copy(),
        }
        n1 = db.sync_to_server_threaded(wait_for_idle=False)
        self.assertEqual(n1, (0, 0))
        self.assertFalse(db.is_worker_busy())

    def test_error(self):
        result = UpdateResult(
            note=self.NOTE.copy(),
            is_updated=False,
            error_object=OSError('connection refused'),
        )
        db = self._patched_db(se_update_note_to_server=[result, result])
        db.notes = {
            'a': self.NOTE.copy(),
        }
        n1 = db.sync_to_server_threaded(wait_for_idle=False)
        self.assertEqual(n1, (0, 0))
        self._wait_worker(db)
        n2 = db.sync_to_server_threaded(wait_for_idle=False)
        self.assertEqual(n2, (0, 1))
        self.assertEqual(db.notes, {
            'a': self.NOTE.copy(),
        })

    def test_new_note(self):
        with patch('time.time', side_effect=itertools.repeat(99)):
            result = UpdateResult(
                note=self.NOTE_MODIFIED.copy(),
                is_updated=True,
                error_object=None,
            )
            db = self._patched_db(se_update_note_to_server=[result])
            db.notes = {
                'local-key': self.NEW_LOCAL_NOTE.copy(),
            }
            n1 = db.sync_to_server_threaded(wait_for_idle=False)
            self.assertEqual(n1, (0, 0))
            self._wait_worker(db)
            n2 = db.sync_to_server_threaded(wait_for_idle=False)
            self.assertEqual(n2, (1, 0))
            self.assertEqual(db.notes, {
                'local-key': self.NOTE_MODIFIED.copy(),
            })

    def test_skip_sync(self):
        result = UpdateResult(
            note=self.SYNCED_NOTE,
            is_updated=False,
            error_object=None,
        )
        db = self._patched_db(se_update_note_to_server=[result])
        db.notes = {
            'a': self.SYNCED_NOTE,
        }
        n1 = db.sync_to_server_threaded(wait_for_idle=False)
        self.assertEqual(n1, (0, 0))
        self.assertFalse(db.is_worker_busy())
