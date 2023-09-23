import os
import shutil
from pathlib import Path

from nvpy.nvpy import Config
from nvpy.notes_db import NotesDB


class DBMixin:
    """ Mixin class for test cases of the NotesDB class. """
    BASE_DIR = '/tmp/.nvpyUnitTests'

    def setUp(self):
        if os.path.isdir(self.BASE_DIR):
            shutil.rmtree(self.BASE_DIR)

    def _mock_config(self, notes_as_txt=False, simplenote_sync=False):
        app_dir = os.path.abspath('nvpy')

        mockConfig = Config(app_dir, [])
        mockConfig.sn_username = ''
        mockConfig.sn_password = ''
        mockConfig.db_path = self.BASE_DIR
        mockConfig.txt_path = self.BASE_DIR + '/notes'
        mockConfig.simplenote_sync = simplenote_sync
        mockConfig.notes_as_txt = notes_as_txt
        mockConfig.replace_filename_spaces = False

        return mockConfig

    def _db(self, notes_as_txt=False, simplenote_sync=False):
        return NotesDB(self._mock_config(notes_as_txt, simplenote_sync))

    def _json_files(self):
        path = Path(self._mock_config().db_path)
        yield from (f.name for f in path.iterdir())

    def _text_files(self):
        path = Path(self._mock_config().txt_path)
        yield from (f.name for f in path.iterdir())
