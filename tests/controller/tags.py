import unittest
from nvpy.nvpy import Controller
from nvpy.nvpy import Config
import os
from nvpy import events
import shutil


class Tags(unittest.TestCase):
    def setUp(self):
        if os.path.isdir('/tmp/.nvpyUnitTests'):
            shutil.rmtree('/tmp/.nvpyUnitTests')

        self.controller = Controller(self.__mock_config())

    def tearDown(self):
        self.controller.view.close()

    def __mock_config(self):
        app_dir = os.path.abspath('nvpy')

        mockConfig = Config(app_dir, [])
        mockConfig.sn_username = ''
        mockConfig.sn_password = ''
        mockConfig.db_path = '/tmp/.nvpyUnitTests'
        mockConfig.txt_path = '/tmp/.nvpyUnitTests/notes'
        mockConfig.simplenote_sync = 0

        return mockConfig

    def test_tag_buttons_are_updated_when_updating_tags_on_a_note(self):
        self.controller.observer_view_create_note(self.controller.view, "create:note",
                                                  events.NoteCreatedEvent(title='aNote'))

        self.controller.view.tags_entry_var.set('atag,anotherTag')
        self.controller.view.handler_add_tags_to_selected_note()

        tag_elements = self.controller.view.note_existing_tags_frame.children.values()
        self.assertEqual(len(tag_elements), 2)

    def test_tag_is_deleted_from_note_when_tag_button_is_clicked(self):
        self.controller.observer_view_create_note(self.controller.view, "create:note",
                                                  events.NoteCreatedEvent(title='aNote'))

        self.controller.view.tags_entry_var.set('aTag')
        self.controller.view.handler_add_tags_to_selected_note()

        self.controller.view.handler_delete_tag_from_selected_note('aTag')

        tag_elements = self.controller.view.note_existing_tags_frame.children.values()
        self.assertEqual(len(tag_elements), 0)

    def test_tag_can_be_added_to_note(self):
        self.controller.observer_view_create_note(self.controller.view, "create:note",
                                                  events.NoteCreatedEvent(title='aNote'))

        self.controller.view.tags_entry_var.set('aTag')
        self.controller.view.handler_add_tags_to_selected_note()

        tag_elements = self.controller.view.note_existing_tags_frame.children.values()
        self.assertEqual(len(tag_elements), 1)
        self.assertEqual(self.controller.view.tags_entry_var.get(), '')


if __name__ == '__main__':
    unittest.main()
