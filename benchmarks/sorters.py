import functools
import unittest

from nvpy import nvpy, notes_db
from benchmarks import Benchmark

notes_10k = [
    notes_db.NoteInfo(
        key='',
        note={
            'content': chr(ord('a') + y) + str(x),
        },
        tagfound=0,
    ) for y in range(10) for x in range(1000)
]
assert len(notes_10k) == 10000


class BenchmarkSorters(unittest.TestCase):

    def test_nop_10k_10times(self):
        for i in range(10):
            sorted(notes_10k, key=notes_db.NopSorter())

    def test_pinnged_10k_10times(self):
        for i in range(10):
            sorted(notes_10k, key=notes_db.PinnedSorter())

    def test_alpha_10k_10times(self):
        for i in range(10):
            sorted(notes_10k, key=notes_db.AlphaSorter())

    def test_alphanum_10k_10times(self):
        for i in range(10):
            sorted(notes_10k, key=notes_db.AlphaNumSorter())

    def test_date_10k_10times(self):
        for i in range(10):
            sorted(notes_10k, key=notes_db.DateSorter(nvpy.SortMode.MODIFICATION_DATE))


def bench_sorter(notes, sorter):
    sorted(notes, key=sorter)


def nop():
    pass


def main():
    sorters = [
        notes_db.NopSorter(),
        notes_db.PinnedSorter(),
        notes_db.AlphaSorter(),
        notes_db.AlphaNumSorter(),
        notes_db.DateSorter(nvpy.SortMode.MODIFICATION_DATE),
    ]
    for sorter in sorters:
        Benchmark(
            label=f'sorter/notes_10k/{sorter.__class__.__name__}',
            setup=nop,
            func=functools.partial(bench_sorter, notes_10k, sorter),
        ).run()


if __name__ == '__main__':
    main()
