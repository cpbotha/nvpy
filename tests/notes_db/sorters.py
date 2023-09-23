import unittest

from nvpy import notes_db
from nvpy import nvpy

Nullable = notes_db.AlphaNumSorter.Nullable


def create_note(title, createdate=1, modifydate=2) -> notes_db.NoteInfo:
    return notes_db.NoteInfo(
        key='xxx',
        note={
            'content': title,
            'createdate': createdate,
            'modifydate': modifydate,
        },
        tagfound=0,
    )


class AlphaNumSorter_Nullable(unittest.TestCase):

    def test_nullable_can_compare_with_int_and_int(self):
        a = Nullable(2)
        b = Nullable(1)
        c = Nullable(2)
        self.assertFalse(a < b)
        self.assertFalse(a == b)
        self.assertTrue(a == c)
        self.assertTrue(a > b)

    def test_nullable_can_compare_with_int_and_none(self):
        a = Nullable(2)
        b = Nullable(None)
        self.assertFalse(a < b)
        self.assertFalse(a == b)
        self.assertTrue(a > b)

    def test_nullable_can_compare_with_none_and_int(self):
        a = Nullable(None)
        b = Nullable(2)
        self.assertTrue(a < b)
        self.assertFalse(a == b)
        self.assertFalse(a > b)

    def test_nullable_can_reprable(self):
        a = Nullable(None)
        b = Nullable(1)
        c = Nullable('c')
        self.assertEqual(repr(a), 'Nullable(None)')
        self.assertEqual(repr(b), 'Nullable(1)')
        self.assertEqual(repr(c), "Nullable('c')")


class AlphaNumSorter(unittest.TestCase):

    def make_sort_key(self, title):
        return notes_db.AlphaNumSorter()(create_note(title))

    def test_sort_keys(self):
        Element = notes_db.AlphaNumSorter.Element

        self.assertTupleEqual(
            self.make_sort_key('foo'),
            (Element(digits=Nullable(None), letters=Nullable('foo'), other=Nullable(None)), ),
        )
        self.assertTupleEqual(
            self.make_sort_key('123'),
            (Element(digits=Nullable(123), letters=Nullable(None), other=Nullable(None)), ),
        )
        self.assertTupleEqual(
            self.make_sort_key('123-foo'),
            (
                Element(digits=Nullable(123), letters=Nullable(None), other=Nullable(None)),
                Element(digits=Nullable(None), letters=Nullable(None), other=Nullable('-')),
                Element(digits=Nullable(None), letters=Nullable('foo'), other=Nullable(None)),
            ),
        )
        self.assertTupleEqual(
            self.make_sort_key('foo#123@bar'),
            (
                Element(digits=Nullable(None), letters=Nullable('foo'), other=Nullable(None)),
                Element(digits=Nullable(None), letters=Nullable(None), other=Nullable('#')),
                Element(digits=Nullable(123), letters=Nullable(None), other=Nullable(None)),
                Element(digits=Nullable(None), letters=Nullable(None), other=Nullable('@')),
                Element(digits=Nullable(None), letters=Nullable('bar'), other=Nullable(None)),
            ),
        )

    def test_sort_order(self):
        sorter = notes_db.AlphaNumSorter()
        notes = [
            create_note(''),
            create_note('abcd'),
            create_note('abcd-'),
            create_note('abcd-200'),
            create_note('abcd-2#a'),
            create_note('bcd-200'),
            create_note('10-xyz'),
            create_note('10-abc'),
            create_note('1.2-xxx'),
            create_note('1.10-yyy'),
            create_note('7|foo'),
        ]
        self.assertSequenceEqual(
            sorted(notes, key=sorter),
            [
                create_note(''),
                create_note('abcd'),
                create_note('abcd-'),
                create_note('abcd-2#a'),
                create_note('abcd-200'),
                create_note('bcd-200'),
                create_note('1.2-xxx'),
                create_note('1.10-yyy'),
                create_note('7|foo'),
                create_note('10-abc'),
                create_note('10-xyz'),
            ],
        )


class DateSorter(unittest.TestCase):

    def test_sort_by_modification_date(self):
        sorter = notes_db.DateSorter(nvpy.SortMode.MODIFICATION_DATE)
        notes = [
            create_note('zzz', createdate=99, modifydate=1),
            create_note('yyy', createdate=96, modifydate=2),
            create_note('www', createdate=98, modifydate=3),
            create_note('xxx', createdate=97, modifydate=4),
        ]
        self.assertSequenceEqual(
            sorted(notes, key=sorter),
            [
                create_note('xxx', createdate=97, modifydate=4),
                create_note('www', createdate=98, modifydate=3),
                create_note('yyy', createdate=96, modifydate=2),
                create_note('zzz', createdate=99, modifydate=1),
            ],
        )

    def test_sort_by_creation_date(self):
        sorter = notes_db.DateSorter(nvpy.SortMode.CREATION_DATE)
        notes = [
            create_note('zzz', createdate=1, modifydate=99),
            create_note('yyy', createdate=2, modifydate=96),
            create_note('www', createdate=3, modifydate=98),
            create_note('xxx', createdate=4, modifydate=97),
        ]
        self.assertSequenceEqual(
            sorted(notes, key=sorter),
            [
                create_note('xxx', createdate=4, modifydate=97),
                create_note('www', createdate=3, modifydate=98),
                create_note('yyy', createdate=2, modifydate=96),
                create_note('zzz', createdate=1, modifydate=99),
            ],
        )

    def test_fail_if_unexpected_mode_specified(self):
        with self.assertRaises(ValueError):
            notes_db.DateSorter(nvpy.SortMode.ALPHA)
        with self.assertRaises(ValueError):
            notes_db.DateSorter(2)
        with self.assertRaises(ValueError):
            notes_db.DateSorter('creation_date')
