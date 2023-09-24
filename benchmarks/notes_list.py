import functools
import os
import shutil

from nvpy.nvpy import Config, NotesListModel
from nvpy.view import View, NoteConfig
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


view = None


def setup(notes_count):
    if os.path.isdir('/tmp/.nvpyUnitTests'):
        shutil.rmtree('/tmp/.nvpyUnitTests')

    global notes_list
    notes_list = NotesListModel()
    notes_list.set_list([
        (
            f'key{i}',
            {
                'content': "title",
                'modifydate': "12345",
                'createdate': "12333",
                'savedate': 0,  # never been written to disc
                'syncdate': 0,  # never been synced with server
                'tags': ['atag', 'anotherTag']
            },
        ) for i in range(notes_count)
    ])

    global view
    if not view:
        view = View(__mock_config(), notes_list)


def bench_refresh_notes_list_view():
    view.notes_list.clear()
    for key, note in notes_list.list:
        view.notes_list.append(note, NoteConfig(tagfound=0, match_regexp=None))


def main():
    for count in [10, 100, 1000, 10000]:
        Benchmark(
            label=f'refresh_notes_list_view/{count}_notes',
            setup=functools.partial(setup, count),
            func=bench_refresh_notes_list_view,
        ).run()


if __name__ == '__main__':
    main()
