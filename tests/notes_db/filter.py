import os
import shutil
import unittest
import copy
from nvpy.nvpy import Config
from nvpy.notes_db import NotesDB

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


class FilterGstyle(unittest.TestCase):
    BASE_DIR = '/tmp/.nvpyUnitTests'

    def setUp(self):
        if os.path.isdir(self.BASE_DIR):
            shutil.rmtree(self.BASE_DIR)

    def __mock_config(self, notes_as_txt=False):
        app_dir = os.path.abspath('nvpy')

        mockConfig = Config(app_dir, [])
        mockConfig.sn_username = ''
        mockConfig.sn_password = ''
        mockConfig.db_path = self.BASE_DIR
        mockConfig.txt_path = self.BASE_DIR + '/notes'
        mockConfig.simplenote_sync = 0
        mockConfig.notes_as_txt = notes_as_txt
        return mockConfig

    def test_search_by_none_or_empty(self):
        db = NotesDB(self.__mock_config())
        db.notes = copy.deepcopy(notes)
        filtered_notes, match_regexp, active_notes = db.filter_notes_gstyle()
        self.assertEqual(len(filtered_notes), 3)
        self.assertEqual(match_regexp, '')
        self.assertEqual(active_notes, 3)
        filtered_notes, match_regexp, active_notes = db.filter_notes_gstyle('')
        self.assertEqual(len(filtered_notes), 3)
        self.assertEqual(match_regexp, '')
        self.assertEqual(active_notes, 3)

    def test_search_by_tag(self):
        db = NotesDB(self.__mock_config())
        db.notes = copy.deepcopy(notes)
        filtered_notes, match_regexp, active_notes = db.filter_notes_gstyle('tag:foo')
        self.assertEqual(len(filtered_notes), 1)
        self.assertEqual(filtered_notes[0].note['content'], notes['3']['content'])
        self.assertEqual(match_regexp, '')  # Should ignore for tag pattern
        self.assertEqual(active_notes, 3)

    def test_search_by_single_words(self):
        db = NotesDB(self.__mock_config())
        db.notes = copy.deepcopy(notes)
        filtered_notes, match_regexp, active_notes = db.filter_notes_gstyle('note 1 active')
        self.assertEqual(len(filtered_notes), 1)
        self.assertEqual(filtered_notes[0].note['content'], notes['1']['content'])
        self.assertEqual(match_regexp, 'note|1|active')  # Should ignore for tag pattern
        self.assertEqual(active_notes, 3)

    def test_search_by_multi_word(self):
        db = NotesDB(self.__mock_config())
        db.notes = copy.deepcopy(notes)
        filtered_notes, match_regexp, active_notes = db.filter_notes_gstyle('"note 1" active')
        self.assertEqual(len(filtered_notes), 1)
        self.assertEqual(filtered_notes[0].note['content'], notes['1']['content'])
        self.assertEqual(match_regexp, r'note\ 1|active')  # Should ignore for tag pattern
        self.assertEqual(active_notes, 3)


class FilterRegexp(unittest.TestCase):
    BASE_DIR = '/tmp/.nvpyUnitTests'

    def setUp(self):
        if os.path.isdir(self.BASE_DIR):
            shutil.rmtree(self.BASE_DIR)

    def __mock_config(self, notes_as_txt=False):
        app_dir = os.path.abspath('nvpy')

        mockConfig = Config(app_dir, [])
        mockConfig.sn_username = ''
        mockConfig.sn_password = ''
        mockConfig.db_path = self.BASE_DIR
        mockConfig.txt_path = self.BASE_DIR + '/notes'
        mockConfig.simplenote_sync = 0
        mockConfig.notes_as_txt = notes_as_txt
        return mockConfig

    def test_search_by_none_or_empty(self):
        db = NotesDB(self.__mock_config())
        db.notes = copy.deepcopy(notes)
        filtered_notes, match_regexp, active_notes = db.filter_notes_regexp()
        self.assertEqual(len(filtered_notes), 3)
        self.assertEqual(match_regexp, '')
        self.assertEqual(active_notes, 3)
        filtered_notes, match_regexp, active_notes = db.filter_notes_regexp('')
        self.assertEqual(len(filtered_notes), 3)
        self.assertEqual(match_regexp, '')
        self.assertEqual(active_notes, 3)

    def test_search_by_invalid_regexp(self):
        db = NotesDB(self.__mock_config())
        db.notes = copy.deepcopy(notes)
        filtered_notes, match_regexp, active_notes = db.filter_notes_regexp('(deleted')
        self.assertEqual(len(filtered_notes), 3)
        self.assertEqual(match_regexp, '')
        self.assertEqual(active_notes, 3)

    def test_search_by_valid_regexp(self):
        db = NotesDB(self.__mock_config())
        db.notes = copy.deepcopy(notes)
        filtered_notes, match_regexp, active_notes = db.filter_notes_regexp('foo| [12]')
        self.assertEqual(len(filtered_notes), 3)
        self.assertEqual(match_regexp, 'foo| [12]')
        self.assertEqual(active_notes, 3)
