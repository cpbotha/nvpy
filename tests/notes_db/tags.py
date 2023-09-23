import unittest

from ._mixin import DBMixin


class Tags(DBMixin, unittest.TestCase):

    def test_database_can_delete_tags(self):
        notes_db = self._db()
        notes_db.notes = {
            '9': {
                'modifydate': 1424239444.609394,
                'tags': ['aTag', 'anotherTag'],
                'createdate': 1424239444.609394,
                'syncdate': 0,
                'content': 'note',
                'savedate': 0
            }
        }

        notes_db.delete_note_tag('9', 'aTag')

        self.assertEqual(notes_db.notes['9']['tags'], ['anotherTag'])

    def test_database_can_add_tags(self):
        notes_db = self._db()
        notes_db.notes = {
            '9': {
                'modifydate': 1424239444.609394,
                'tags': [],
                'createdate': 1424239444.609394,
                'syncdate': 0,
                'content': 'note',
                'savedate': 0
            }
        }

        notes_db.add_note_tags('9', 'aTag,anotherTag')

        self.assertEqual(notes_db.notes['9']['tags'], ['aTag', 'anotherTag'])


if __name__ == '__main__':
    unittest.main()
