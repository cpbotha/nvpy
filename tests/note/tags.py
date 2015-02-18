import unittest
import ConfigParser 
from mock import Mock
from nvpy.view import View
from nvpy.nvpy import NotesListModel
from nvpy.nvpy import Controller
from nvpy.nvpy import Config
import os
from nvpy import utils
import time
import shutil

class Tags(unittest.TestCase):

    def setUp(self):
        if os.path.isdir('/tmp/.nvpyUnitTests'):
            shutil.rmtree('/tmp/.nvpyUnitTests')

    def __mock_config(self):
        app_dir = os.path.abspath('nvpy')

        mockConfig = Config(app_dir)
        mockConfig.sn_username = ''
        mockConfig.sn_password = ''
        mockConfig.db_path = '/tmp/.nvpyUnitTests'
        mockConfig.txt_path = '/tmp/.nvpyUnitTests/notes'
        mockConfig.simplenote_sync = 0

	return mockConfig

    def test_tag_buttons_are_created_when_displaying_a_note(self):
        mockNotesListModel = NotesListModel()

        mockNotesListModel.add_observer = Mock()
        
	view = View(self.__mock_config(), mockNotesListModel)

        note = {
            'content': "title",
            'modifydate': "timestamp",
            'createdate': "timestamp",
            'savedate': 0,  # never been written to disc
            'syncdate': 0,  # never been synced with server
            'tags': ['atag', 'anotherTag']
        }

	view.set_note_data(note)

        tag_elements = view.note_existing_tags_frame.children.values() 

	for element in tag_elements:
            self.assertEqual(element.__class__.__name__, 'Button', "Tag element was not a button")
            self.assertTrue(element['text'] in ['atag x', 'anotherTag x'], "Didn't expect to find a tag with text %s" % element['text'] )
        
	self.assertEqual(len(tag_elements), 2) 
        view.close()
    
    def test_tag_buttons_are_updated_when_updating_tags_on_a_note(self):
        controller = Controller(self.__mock_config())	
        
	controller.observer_view_create_note(controller.view, "create:note", utils.KeyValueObject(title='aNote'))
	
	controller.view.tags_entry_var.set('atag,anotherTag')
        
        tag_elements = controller.view.note_existing_tags_frame.children.values() 
        self.assertEqual(len(tag_elements), 2)
	
        controller.view.close()
    
    def test_tag_is_deleted_from_note_when_tag_button_is_clicked(self): 
        controller = Controller(self.__mock_config())	
        
	controller.observer_view_create_note(controller.view, "create:note", utils.KeyValueObject(title='aNote'))
	
	controller.view.tags_entry_var.set('aTag')

	controller.view.handler_delete_tag_from_selected_note('aTag')
        
        tag_elements = controller.view.note_existing_tags_frame.children.values() 
        self.assertEqual(len(tag_elements), 0)
	
        controller.view.close()
    
        
if __name__ == '__main__':
    unittest.main()
