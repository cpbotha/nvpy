import unittest
import ConfigParser 
from mock import Mock
from nvpy.nvpy import Config
from nvpy.notes_db import NotesDB
import os
import shutil


class Tags(unittest.TestCase):

    def setUp(self):
        if os.path.isdir('/tmp/.nvpyUnitTests'):
            shutil.rmtree('/tmp/.nvpyUnitTests')

    def __mock_config(self):
        app_dir = os.path.abspath('nvpy')

        mockConfig = Config(app_dir)
        mockConfig.sn_username = ''
        mockConfig.sn_password = ''
        mockConfig.db_path = '/tmp/.nvpyUnitTests'
        mockConfig.txt_path = '/tmp/.nvpyUnitTests/notes'
        mockConfig.simplenote_sync = 0

        return mockConfig

    def test_database_can_delete_tags(self):
        notes_db = NotesDB(self.__mock_config())
        notes_db.notes = {'9': {'modifydate': 1424239444.609394, 'tags': ['aTag', 'anotherTag'], 'createdate': 1424239444.609394, 'syncdate': 0, 'content': 'note', 'savedate': 0}}

        notes_db.delete_note_tag('9', 'aTag')

        self.assertEqual(notes_db.notes['9']['tags'], ['anotherTag'])
    
    def test_database_can_add_tags(self):
        notes_db = NotesDB(self.__mock_config())
        notes_db.notes = {'9': {'modifydate': 1424239444.609394, 'tags': [], 'createdate': 1424239444.609394, 'syncdate': 0, 'content': 'note', 'savedate': 0}}

        notes_db.add_note_tags('9', 'aTag,anotherTag')

        self.assertEqual(notes_db.notes['9']['tags'], ['aTag', 'anotherTag'])
        
if __name__ == '__main__':
    unittest.main()
