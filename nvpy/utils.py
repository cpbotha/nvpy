# nvPY: cross-platform note-taking app with simplenote syncing
# copyright 2012 by Charl P. Botha <cpbotha@vxlabs.com>
# new BSD license

import random
import re
import urllib2

# first line with non-whitespace should be the title
note_title_re = re.compile('\s*(.*)\n?')
        
def generate_random_key():
    """Generate random 30 digit (15 byte) hex string.
    
    stackoverflow question 2782229
    """
    return '%030x' % (random.randrange(256**15),)

def get_note_title(note):
    mo = note_title_re.match(note.get('content', ''))
    if mo:
        return mo.groups()[0]
    else:
        return ''
    


def check_internet_on():
    """Utility method to check if we have an internet connection.
    
    slightly adapted from: http://stackoverflow.com/a/3764660/532513
    """
    try:
        urllib2.urlopen('http://74.125.113.99',timeout=1)
        return True
    
    except urllib2.URLError: 
        pass
    
    return False    

class KeyValueObject:
    """Store key=value pairs in this object and retrieve with o.key.
    
    You should also be able to do MiscObject(**your_dict) for the same effect.
    """

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

class SubjectMixin:
    """Maintain a list of callables for each event type.
    
    We follow the convention action:object, e.g. change:entry.
    """

    def __init__(self):
        self.observers = {}
        self.mutes = {}

    def add_observer(self, evt_type, o):
        if evt_type not in self.observers:
            self.observers[evt_type] = [o]
        
        elif o not in self.observers[evt_type]:
            self.observers[evt_type].append(o)
        
    def notify_observers(self, evt_type, evt):
        if evt_type in self.mutes or evt_type not in self.observers:
            return
        
        for o in self.observers[evt_type]:
            # invoke observers with ourselves as first param
            o(self, evt_type, evt)
            
    def mute(self, evt_type):
        self.mutes[evt_type] = True
        
    def unmute(self, evt_type):
        if evt_type in self.mutes:
            del self.mutes[evt_type]
