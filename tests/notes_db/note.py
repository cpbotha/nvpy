import unittest
import itertools
import copy
from unittest.mock import patch

from nvpy.notes_db import Note, NoteStatus
from ._mixin import DBMixin


class NoteComparators(unittest.TestCase):

    def test_need_save(self):
        a = Note({'modifydate': 2, 'savedate': 1, 'syncdate': 0})
        b = Note({'modifydate': 2, 'savedate': 2, 'syncdate': 0})
        c = Note({'modifydate': 2, 'savedate': 3, 'syncdate': 0})
        self.assertTrue(a.need_save)
        self.assertFalse(b.need_save)
        self.assertFalse(c.need_save)

    def test_need_sync_to_server(self):
        a = Note({'modifydate': 2, 'syncdate': 2})
        b = Note({'modifydate': 2, 'syncdate': 1, 'key': 'note_id'})
        c = Note({'modifydate': 2, 'syncdate': 2, 'key': 'note_id'})
        d = Note({'modifydate': 2, 'syncdate': 3, 'key': 'note_id'})
        self.assertTrue(a.need_sync_to_server)
        self.assertTrue(b.need_sync_to_server)
        self.assertFalse(c.need_sync_to_server)
        self.assertFalse(d.need_sync_to_server)

    def test_is_newer_than(self):
        a = Note({'modifydate': 1})
        b = Note({'modifydate': 2})
        c = Note({'modifydate': 3})
        self.assertTrue(b.is_newer_than(a))
        self.assertFalse(b.is_newer_than(b))
        self.assertFalse(b.is_newer_than(c))


class NotesDBComparators(DBMixin, unittest.TestCase):

    def test_is_different_note(self):
        db = self._db()
        # If all fields excluding nvPY internal fields are same, those are same.
        self.assertFalse(
            db.is_different_note(
                {
                    'content': 'foo',
                    'modifydate': 2,
                    'savedate': 5,  # ignore
                    'syncdate': 8,  # ignore
                },
                {
                    'content': 'foo',
                    'modifydate': 2,
                },
            ))
        # If content is not same, those are different.
        self.assertTrue(
            db.is_different_note(
                {
                    'content': 'foo',
                    'modifydate': 2,
                    'savedate': 5,  # ignore
                    'syncdate': 8,  # ignore
                },
                {
                    'content': 'bar',  # changed
                    'modifydate': 2,
                },
            ))
        # If other fields excluding nvPY internal fields are not same, those are different.
        self.assertTrue(
            db.is_different_note(
                {
                    'content': 'foo',
                    'modifydate': 2,
                    'savedate': 5,  # ignore
                    'syncdate': 8,  # ignore
                },
                {
                    'content': 'foo',
                    'modifydate': 3,  # changed
                },
            ))
        # Must accept non-hashable object like list.
        self.assertFalse(
            db.is_different_note(
                {
                    'tags': ['a', 'b'],
                    'savedate': 5,  # ignore
                    'syncdate': 8,  # ignore
                },
                {
                    'tags': ['a', 'b'],
                },
            ))


class NoteOperations(DBMixin, unittest.TestCase):
    NOTES = {
        'KEY': {
            'key': 'KEY',
            'content': 'example note',
            'createdate': 1,
            'modifydate': 2,
            'savedate': 3,
        },
    }

    def test_delete(self):
        db = self._db()
        db.notes = copy.deepcopy(self.NOTES)
        with patch('time.time', side_effect=itertools.repeat(99)):
            db.delete_note('KEY')
        self.assertEqual(
            db.notes['KEY'],
            {
                'key': 'KEY',
                'content': 'example note',
                'deleted': 1,
                'createdate': 1,
                'modifydate': 99,
                'savedate': 3,
            },
        )

    def test_get(self):
        db = self._db()
        db.notes = copy.deepcopy(self.NOTES)
        with self.assertRaises(KeyError):
            db.get_note('NOT_FOUND')
        note = db.get_note('KEY')
        self.assertEqual(note, self.NOTES['KEY'])

    def test_get_content(self):
        db = self._db()
        db.notes = copy.deepcopy(self.NOTES)
        content = db.get_note_content('KEY')
        self.assertEqual(content, self.NOTES['KEY']['content'])

    def test_get_status(self):
        db = self._db()
        db.notes = {
            'MODIFIED': {
                'modifydate': 3,
                'savedate': 1,
                'syncdate': 2,
            },
            'SAVED': {
                'modifydate': 2,
                'savedate': 3,
                'syncdate': 1,
            },
            'SYNCED': {
                'modifydate': 1,
                'savedate': 2,
                'syncdate': 3,
            },
            'SYNCED_BUT_NOT_SAVED': {
                'modifydate': 2,
                'savedate': 1,
                'syncdate': 3,
            }
        }
        self.assertEqual(db.get_note_status('MODIFIED'),
                         NoteStatus(saved=False, synced=False, modified=True, full_syncing=False))
        self.assertEqual(db.get_note_status('SAVED'),
                         NoteStatus(saved=True, synced=False, modified=False, full_syncing=False))
        self.assertEqual(db.get_note_status('SYNCED'),
                         NoteStatus(saved=True, synced=True, modified=False, full_syncing=False))
        # todo: NoteStatus.modified = not NoteStatus.saved. NoteStatus.modified can be replace to the property.
        self.assertEqual(db.get_note_status('SYNCED_BUT_NOT_SAVED'),
                         NoteStatus(saved=False, synced=True, modified=True, full_syncing=False))

    def assertTags(self, expected: list, note):
        self.assertEqual(set(expected), set(note['tags']))

    def test_delete_tag(self):
        db = self._db()
        db.notes = {'KEY': {'tags': ['foo', 'bar']}}
        with self.assertRaises(ValueError):
            db.delete_note_tag('KEY', 'not-found')
        self.assertTags(['foo', 'bar'], db.notes['KEY'])
        db.delete_note_tag('KEY', 'bar')
        self.assertTags(['foo'], db.notes['KEY'])

    def test_add_tags(self):
        db = self._db()
        # Add a tag.
        db.notes = {'KEY': {'tags': ['foo', 'bar']}}
        db.add_note_tags('KEY', 'baz')
        self.assertTags(['foo', 'bar', 'baz'], db.notes['KEY'])
        # Add comma separated tags.
        db.notes = {'KEY': {'tags': ['foo', 'bar']}}
        db.add_note_tags('KEY', 'baz,qux,quux')
        self.assertTags(['foo', 'bar', 'baz', 'qux', 'quux'], db.notes['KEY'])
        # Add comma separated tags with spaces.
        db.notes = {'KEY': {'tags': ['foo', 'bar']}}
        db.add_note_tags('KEY', 'baz, qux, quux')
        self.assertTags(['foo', 'bar', 'baz', 'qux', 'quux'], db.notes['KEY'])
        # Add space separated tags.
        db.notes = {'KEY': {'tags': ['foo', 'bar']}}
        db.add_note_tags('KEY', 'baz qux quux')
        # TODO: なんかバグっている
        # self.assertTags(['foo', 'bar', 'baz', 'qux', 'quux'], db.notes['KEY'])
