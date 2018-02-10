import platform
import unittest

from tests.helpers.pydevd import FakePyDevd
from tests.helpers.vsc import FakeVSC


OS_ID = 'WINDOWS' if platform.system() == 'Windows' else 'UNIX'


class HighlevelTestCase(unittest.TestCase):

    def new_fake(self, pydevd=None, handler=None):
        if pydevd is None:
            pydevd = FakePyDevd()
        vsc = FakeVSC(pydevd.start, handler)
        self.addCleanup(vsc.close)

        return vsc, pydevd
