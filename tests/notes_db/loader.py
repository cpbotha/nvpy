import os
import shutil
import unittest
import pathlib
import json
from nvpy.nvpy import Config
from nvpy.notes_db import NotesDB

now = 1111111444
note1 = {
    'modifydate': 1111111222,
    'tags': [],
    'createdate': 1111111111,
    'syncdate': 0,
    'content': 'note',
    'savedate': now,
}
note2 = {
    'modifydate': 1111111333,
    'tags': [],
    'createdate': 1111111222,
    'syncdate': 0,
    'content': 'another note\nfoo bar',
    'savedate': now,
}


class Loader(unittest.TestCase):
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

    @property
    def __json_dir(self) -> pathlib.Path:
        dir = pathlib.Path(self.BASE_DIR)
        if not dir.is_dir():
            dir.mkdir()
        return dir

    @property
    def __text_dir(self) -> pathlib.Path:
        dir = self.__json_dir / 'notes'
        if not dir.is_dir():
            dir.mkdir()
        return dir

    def __write_json(self, key: str, data):
        fpath = self.__json_dir / (key + '.json')
        with fpath.open('w') as f:
            json.dump(data, f)

    def __write_text(self, key: str, data: str):
        fpath = self.__text_dir / (key + '.txt')
        with fpath.open('w') as f:
            f.write(data)

    def test_database_can_load_from_empty_dir(self):
        db = NotesDB(self.__mock_config())
        self.assertDictEqual(db.notes, {})

    def test_database_can_load_json_files(self):
        self.__write_json('1', note1)
        self.__write_json('2', note2)
        db = NotesDB(self.__mock_config())
        self.assertSetEqual(set(db.notes.keys()), {'1', '2'})

    def test_database_can_load_from_text_files(self):
        self.__write_json('1', note1)
        self.__write_json('2', note2)
        self.__write_text('note', note1['content'])
        self.__write_text('another_note', note2['content'])
        db = NotesDB(self.__mock_config(notes_as_txt=True))
        self.assertSetEqual(set(db.notes.keys()), {'1', '2'})
        self.assertEqual(db.notes['1']['content'], note1['content'])
        self.assertEqual(db.notes['2']['content'], note2['content'])
