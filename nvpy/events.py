import typing


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
    tags: typing.List[str]


class TagRemovedEvent(typing.NamedTuple):
    tag: str


class NoteStatusChangedEvent(typing.NamedTuple):
    what: str
    key: str


class NoteSavedEvent(typing.NamedTuple):
    key: str


class NoteSyncedEvent(typing.NamedTuple):
    lkey: str
    old_note: typing.Any


class SyncCompletedEvent(typing.NamedTuple):
    errors: int


class SyncFailedEvent(typing.NamedTuple):
    error: BaseException
    exc_info: typing.Any


class SyncProgressEvent(typing.NamedTuple):
    msg: str


class SortModeChangedEvent(typing.NamedTuple):
    mode: str


class PinnedOnTopChangedEvent(typing.NamedTuple):
    pinned_on_top: bool
