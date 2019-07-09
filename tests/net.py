# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

"""Test helpers for networking.
"""

import os
import re
import requests
import socket
import threading
import time

from ptvsd.common import compat, fmt, log
from tests.patterns import some


def get_test_server_port(start, stop):
    """Returns a server port number that can be safely used for listening without
    clashing with another test worker process, when running with pytest-xdist.

    If multiple test workers invoke this function with the same min value, each of
    them will receive a different number that is not lower than start (but may be
    higher). If the resulting value is >=stop, it is a fatal error.

    Note that if multiple test workers invoke this function with different ranges
    that overlap, conflicts are possible!
    """

    try:
        worker_id = compat.force_ascii(os.environ['PYTEST_XDIST_WORKER'])
    except KeyError:
        n = 0
    else:
        assert worker_id == some.str.matching(br"gw(\d+)"), (
            "Unrecognized PYTEST_XDIST_WORKER format"
        )
        n = int(worker_id[2:])

    port = start + n
    assert port <= stop
    return port


def find_http_url(text):
    match = re.search(r"https?://[-.0-9A-Za-z]+(:\d+)/?", text)
    return match.group() if match else None


def wait_until_port_is_listening(port, interval=1, max_attempts=1000):
    """Blocks until the specified TCP port on localhost is listening, and can be
    connected to.

    Tries to connect to the port periodically, and repeats until connection succeeds.
    Connection is immediately closed before returning.
    """

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        for i in compat.xrange(0, max_attempts):
            try:
                log.info("Trying to connect to port {0} (attempt {1})", port, i)
                sock.connect(("localhost", port))
                return
            except socket.error:
                time.sleep(interval)
    finally:
        sock.close()


class WebRequest(object):
    """An async wrapper around requests.
    """

    @staticmethod
    def get(*args, **kwargs):
        return WebRequest("get", *args, **kwargs)

    @staticmethod
    def post(*args, **kwargs):
        return WebRequest("post", *args, **kwargs)

    def __init__(self, method, url, *args, **kwargs):
        """Invokes requests.method(url, *args, **kwargs) on a background thread,
        and immediately returns.
        """

        self.request = None
        """The underlying Request object. Not set until wait_for_response() returns.
        """

        method = getattr(requests, method)
        self._worker_thread = threading.Thread(
            target=lambda: self._worker(method, url, *args, **kwargs),
            name=fmt("WebRequest({0!r})", url)
        )

    def _worker(self, method, url, *args, **kwargs):
        self.request = method(url, *args, **kwargs)

    def wait_for_response(self, timeout=None):
        """Blocks until the request completes, and returns self.request.
        """
        self._worker_thread.join(timeout)
        return self.request

    def response_text(self):
        """Blocks until the request completes, and returns the response body.
        """
        return self.wait_for_response().text


class WebServer(object):
    """Interacts with a web server listening on localhost on the specified port.
    """

    def __init__(self, port):
        self.port = port
        self.url = fmt("http://localhost:{0}", port)

    def __enter__(self):
        """Blocks until the server starts listening on self.port.
        """
        wait_until_port_is_listening(self.port)
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        """Sends an HTTP /exit POST request to the server.
        """
        self.post("exit").wait_for_response()

    def get(self, path, *args, **kwargs):
        return WebRequest.get(self.url + path, *args, **kwargs)

    def post(self, path, *args, **kwargs):
        return WebRequest.post(self.url + path, *args, **kwargs)
