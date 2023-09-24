import functools
import os
import shutil
import typing

from nvpy.nvpy import Config, NotesListModel
from nvpy.view import View, NoteConfig
from nvpy.notes_db import NoteInfo
from benchmarks import Benchmark


def __mock_config():
    app_dir = os.path.abspath('nvpy')

    mockConfig = Config(app_dir, [])
    mockConfig.sn_username = ''
    mockConfig.sn_password = ''
    mockConfig.db_path = '/tmp/.nvpyUnitTests'
    mockConfig.txt_path = '/tmp/.nvpyUnitTests/notes'
    mockConfig.simplenote_sync = 0
    return mockConfig


notes_list: typing.Optional[NotesListModel] = None
view: typing.Optional[View] = None


def setup(notes_count):
    if os.path.isdir('/tmp/.nvpyUnitTests'):
        shutil.rmtree('/tmp/.nvpyUnitTests')

    global notes_list
    notes_list = NotesListModel()
    notes_list.set_list([
        NoteInfo(
            key=f'key{i}',
            note={
                'content': "title",
                'modifydate': "12345",
                'createdate': "12333",
                'savedate': 0,  # never been written to disc
                'syncdate': 0,  # never been synced with server
                'tags': ['atag', 'anotherTag']
            },
            tagfound=False,
        ) for i in range(notes_count)
    ])

    global view
    if not view:
        view = View(__mock_config(), notes_list)


def bench_refresh_notes_list_view():
    view.notes_list.clear()
    for ni in notes_list.list:
        view.notes_list.append(ni.note, NoteConfig(tagfound=ni.tagfound, match_regexp=None))


def main():
    for count in [10, 100, 1000, 10000]:
        Benchmark(
            label=f'refresh_notes_list_view/{count}_notes',
            setup=functools.partial(setup, count),
            func=bench_refresh_notes_list_view,
        ).run()


if __name__ == '__main__':
    main()
