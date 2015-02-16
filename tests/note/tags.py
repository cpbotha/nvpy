import unittest
from mock import Mock
from nvpy.view import View

from nvpy.nvpy import NotesListModel
from nvpy.nvpy import Config


class Tags(unittest.TestCase):
    def test_tags_are_created_when_displaying_a_note(self):
        mockNotesListModel = NotesListModel()
	mockConfig = Config("nvpy")

        mockNotesListModel.add_observer = Mock()
	
	view = View(mockConfig, mockNotesListModel)

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
            self.assertTrue(element['text'] in ['atag', 'anotherTag'], "Didn't expect to find a tag with text %s" % element['text'] )
        
	self.assertEqual(len(tag_elements), 2) 
        
if __name__ == '__main__':
    unittest.main()
