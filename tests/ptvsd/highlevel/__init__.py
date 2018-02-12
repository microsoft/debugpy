import platform
import unittest

from _pydevd_bundle.pydevd_comm import (
    CMD_VERSION,
)

from tests.helpers.pydevd import FakePyDevd
from tests.helpers.vsc import FakeVSC


OS_ID = 'WINDOWS' if platform.system() == 'Windows' else 'UNIX'


class HighlevelTestCase(unittest.TestCase):
    """The base class for high-level ptvsd tests."""

    MIN_INITIALIZE_ARGS = {
        'adapterID': 'spam',
    }

    def next_vsc_seq(self):
        try:
            seq = self._seq
        except AttributeError:
            seq = 0
        self._seq = seq + 1
        return seq

    def new_fake(self, pydevd=None, handler=None):
        """Return a new fake VSC that may be used in tests."""
        if pydevd is None:
            pydevd = FakePyDevd()
        vsc = FakeVSC(pydevd.start, handler)
        self.addCleanup(vsc.close)

        return vsc, pydevd

    def attach(self, vsc, pydevd, **kwargs):
        """Initialize the debugger protocol and then attach."""
        self._handshake(vsc, pydevd, 'attach', **kwargs)

    def launch(self, vsc, pydevd, **kwargs):
        """Initialize the debugger protocol and then launch."""
        self._handshake(vsc, pydevd, 'launch', **kwargs)

    def _handshake(self, vsc, pydevd, command, reset=True, **kwargs):
        initargs = dict(
            kwargs.pop('initargs', None) or {},
            disconnect=kwargs.pop('disconnect', True),
        )
        with vsc.wait_for_event('initialized'):
            self._initialize(vsc, pydevd, **initargs)
            req = {
                'type': 'request',
                'seq': self.next_vsc_seq(),
                'command': command,
                'arguments': kwargs,
            }
            with vsc.wait_for_response(req):
                vsc.send_request(req)
        if reset:
            vsc.reset()
            pydevd.reset()

    def _initialize(self, vsc, pydevd, disconnect=True, **reqargs):
        """
        See https://code.visualstudio.com/docs/extensionAPI/api-debugging#_the-vs-code-debug-protocol-in-a-nutshell
        """  # noqa
        pydevd.add_pending_response(CMD_VERSION, pydevd.VERSION)
        req = {
            'type': 'request',
            'seq': self.next_vsc_seq(),
            'command': 'initialize',
            'arguments':  dict(self.MIN_INITIALIZE_ARGS, **reqargs),
        }
        with vsc.wait_for_response(req):
            vsc.send_request(req)

        if disconnect:
            self.addCleanup(self.disconnect)

    def disconnect(self, vsc, **reqargs):
        req = {
            'type': 'request',
            'seq': self.next_vsc_seq(),
            'command': 'disconnect',
            'arguments': reqargs,
        }
        with vsc.wait_for_response(req):
            vsc.send_request(req)
        # TODO: wait for an exit event?
#        vsc.close()
