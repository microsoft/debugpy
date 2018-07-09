import os.path

from tests import RESOURCES_ROOT
from .workspace import ReadonlyFSTree


class TestResources(ReadonlyFSTree):

    @classmethod
    def from_module(cls, modname):
        parts = modname.split('.')
        assert parts and parts[0] == 'tests'
        root = os.path.join(RESOURCES_ROOT, *parts[1:])
        return cls(root)

    def __init__(self, root):
        root = os.path.abspath(root)
        assert root.startswith(RESOURCES_ROOT)
        super(TestResources, self).__init__(root)
