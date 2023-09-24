import re
import unittest
import copy

from ._mixin import DBMixin

notes = {
    '1': {
        'modifydate': 1111111222,
        'tags': [],
        'createdate': 1111111111,
        'syncdate': 0,
        'content': 'active note 1',
        'savedate': 0,
    },
    '2': {
        'modifydate': 1111111222,
        'tags': [],
        'createdate': 1111111111,
        'syncdate': 0,
        'content': 'active note 2',
        'savedate': 0,
    },
    '3': {
        'modifydate': 1111111222,
        'tags': ['foo'],
        'createdate': 1111111111,
        'syncdate': 0,
        'content': 'active note 3',
        'savedate': 0,
    },
    '4': {
        'modifydate': 1111111222,
        'tags': [],
        'createdate': 1111111111,
        'syncdate': 0,
        'content': 'deleted note',
        'savedate': 0,
        'deleted': True,
    }
}


class FilterGstyle(DBMixin, unittest.TestCase):

    def test_search_by_none_or_empty(self):
        db = self._db()
        db.notes = copy.deepcopy(notes)
        filtered_notes, match_regexp, active_notes = db.filter_notes_gstyle()
        self.assertEqual(len(filtered_notes), 3)
        self.assertEqual(match_regexp, None)
        self.assertEqual(active_notes, 3)
        filtered_notes, match_regexp, active_notes = db.filter_notes_gstyle('')
        self.assertEqual(len(filtered_notes), 3)
        self.assertEqual(match_regexp, None)
        self.assertEqual(active_notes, 3)

    def test_search_by_tag(self):
        db = self._db()
        db.notes = copy.deepcopy(notes)
        filtered_notes, match_regexp, active_notes = db.filter_notes_gstyle('tag:foo')
        self.assertEqual(len(filtered_notes), 1)
        self.assertEqual(filtered_notes[0].note['content'], notes['3']['content'])
        self.assertEqual(match_regexp, None)  # Should ignore for tag pattern
        self.assertEqual(active_notes, 3)

    def test_search_by_single_words(self):
        db = self._db()
        db.notes = copy.deepcopy(notes)
        filtered_notes, match_regexp, active_notes = db.filter_notes_gstyle('note 1 active')
        self.assertEqual(len(filtered_notes), 1)
        self.assertEqual(filtered_notes[0].note['content'], notes['1']['content'])
        self.assertEqual(match_regexp, re.compile('note|1|active', re.I))  # Should ignore for tag pattern
        self.assertEqual(active_notes, 3)

    def test_search_by_multi_word(self):
        db = self._db()
        db.notes = copy.deepcopy(notes)
        filtered_notes, match_regexp, active_notes = db.filter_notes_gstyle('"note 1" active')
        self.assertEqual(len(filtered_notes), 1)
        self.assertEqual(filtered_notes[0].note['content'], notes['1']['content'])
        self.assertEqual(match_regexp, re.compile(r'note\ 1|active', re.I))  # Should ignore for tag pattern
        self.assertEqual(active_notes, 3)


class FilterRegexp(DBMixin, unittest.TestCase):

    def test_search_by_none_or_empty(self):
        db = self._db()
        db.notes = copy.deepcopy(notes)
        filtered_notes, match_regexp, active_notes = db.filter_notes_regexp()
        self.assertEqual(len(filtered_notes), 3)
        self.assertEqual(match_regexp, None)
        self.assertEqual(active_notes, 3)
        filtered_notes, match_regexp, active_notes = db.filter_notes_regexp('')
        self.assertEqual(len(filtered_notes), 3)
        self.assertEqual(match_regexp, None)
        self.assertEqual(active_notes, 3)

    def test_search_by_invalid_regexp(self):
        db = self._db()
        db.notes = copy.deepcopy(notes)
        filtered_notes, match_regexp, active_notes = db.filter_notes_regexp('(deleted')
        self.assertEqual(len(filtered_notes), 3)
        self.assertEqual(match_regexp, None)
        self.assertEqual(active_notes, 3)

    def test_search_by_valid_regexp(self):
        db = self._db()
        db.notes = copy.deepcopy(notes)
        filtered_notes, match_regexp, active_notes = db.filter_notes_regexp('foo| [12]')
        self.assertEqual(len(filtered_notes), 3)
        self.assertEqual(match_regexp, re.compile('foo| [12]', re.M))
        self.assertEqual(active_notes, 3)
