from __future__ import print_function

import contextlib
import os
import time
import sys
import unittest

import ptvsd._util
from ptvsd.socket import create_client, close_socket
from tests.helpers.proc import Proc
from tests.helpers.workspace import Workspace


@contextlib.contextmanager
def _retrier(timeout=1, persec=10, max=None, verbose=False):
    steps = int(timeout * persec) + 1
    delay = 1.0 / persec

    @contextlib.contextmanager
    def attempt(num):
        if verbose:
            print('*', end='')
            sys.stdout.flush()
        yield
        if verbose:
            if num % persec == 0:
                print()
            elif (num * 2) % persec == 0:
                print(' ', end='')

    def attempts():
        # The first attempt always happens.
        num = 1
        with attempt(num):
            yield num
        for num in range(2, steps):
            if max is not None and num > max:
                raise RuntimeError('too many attempts (max {})'.format(max))
            time.sleep(delay)
            with attempt(num):
                yield num
        else:
            raise RuntimeError('timed out')
    yield attempts()
    if verbose:
        print()


class RawConnectionTests(unittest.TestCase):

    VERBOSE = False
    #VERBOSE = True

    def setUp(self):
        super(RawConnectionTests, self).setUp()
        self.workspace = Workspace()
        self.addCleanup(self.workspace.cleanup)

    def _propagate_verbose(self):
        if not self.VERBOSE:
            return

        def unset():
            Proc.VERBOSE = False
            ptvsd._util.DEBUG = False
        self.addCleanup(unset)
        Proc.VERBOSE = True
        ptvsd._util.DEBUG = True

    def _wait_for_ready(self, rpipe):
        if self.VERBOSE:
            print('waiting for ready')
        line = b''
        while True:
            c = os.read(rpipe, 1)
            line += c
            if c == b'\n':
                if self.VERBOSE:
                    print(line.decode('utf-8'), end='')
                if b'getting session socket' in line:
                    break
                line = b''

    @unittest.skip('there is a race here under travis')
    def test_repeated(self):
        def debug(msg):
            if not self.VERBOSE:
                return
            print(msg)

        def connect(addr, wait=None, closeonly=False):
            sock = create_client()
            try:
                sock.settimeout(1)
                sock.connect(addr)
                debug('>connected')
                if wait is not None:
                    debug('>waiting')
                    time.sleep(wait)
            finally:
                debug('>closing')
                if closeonly:
                    sock.close()
                else:
                    close_socket(sock)
        filename = self.workspace.write('spam.py', content="""
            raise Exception('should never run')
            """)
        addr = ('localhost', 5678)
        self._propagate_verbose()
        rpipe, wpipe = os.pipe()
        self.addCleanup(lambda: os.close(rpipe))
        self.addCleanup(lambda: os.close(wpipe))
        proc = Proc.start_python_module('ptvsd', [
            '--server',
            '--wait',
            '--host', 'localhost',
            '--port', '5678',
            '--file', filename,
        ], env={
            'PTVSD_DEBUG': '1',
            'PTVSD_SOCKET_TIMEOUT': '1',
        }, stdout=wpipe)
        with proc:
            # Wait for the server to spin up.
            debug('>a')
            with _retrier(timeout=3, verbose=self.VERBOSE) as attempts:
                for _ in attempts:
                    try:
                        connect(addr)
                        break
                    except Exception:
                        pass
            self._wait_for_ready(rpipe)
            debug('>b')
            connect(addr)
            self._wait_for_ready(rpipe)
            # We should be able to handle more connections.
            debug('>c')
            connect(addr)
            self._wait_for_ready(rpipe)
            # Give ptvsd long enough to try sending something.
            debug('>d')
            connect(addr, wait=0.2)
            self._wait_for_ready(rpipe)
            debug('>e')
            connect(addr)
            self._wait_for_ready(rpipe)
            debug('>f')
            connect(addr, closeonly=True)
            self._wait_for_ready(rpipe)
            debug('>g')
            connect(addr)
            self._wait_for_ready(rpipe)
            debug('>h')
            connect(addr)
            self._wait_for_ready(rpipe)
