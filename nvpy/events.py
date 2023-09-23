""" Event classes used for event delivery with SubjectMixin """

import typing

from . import nvpy


class NoteCreatedEvent(typing.NamedTuple):
    title: str


class NoteSelectionChangedEvent(typing.NamedTuple):
    # Index of selected note.
    sel: int


class CheckboxChangedEvent(typing.NamedTuple):
    value: bool


class TextBoxChangedEvent(typing.NamedTuple):
    value: str


class TagsAddedEvent(typing.NamedTuple):
    # This string is entered from UI. It may be one or more comma-separated tags.
    # We should parse it and clean up before use it.
    tags: str


class TagRemovedEvent(typing.NamedTuple):
    tag: str


class NoteStatusChangedEvent(typing.NamedTuple):
    what: str
    key: str


class NoteSavedEvent(typing.NamedTuple):
    key: str


class NoteSyncedEvent(typing.NamedTuple):
    lkey: str


class SyncCompletedEvent(typing.NamedTuple):
    errors: int


class SyncFailedEvent(typing.NamedTuple):
    error: BaseException
    exc_info: typing.Any


class SyncProgressEvent(typing.NamedTuple):
    msg: str


class SortModeChangedEvent(typing.NamedTuple):
    mode: 'nvpy.SortMode'


class PinnedOnTopChangedEvent(typing.NamedTuple):
    pinned_on_top: bool
