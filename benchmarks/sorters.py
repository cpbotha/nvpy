import unittest
import nvpy.notes_db as notes_db
import benchmarks

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
            sorted(notes_10k, key=notes_db.DateSorter(notes_db.SortMode.MODIFICATION_DATE))
