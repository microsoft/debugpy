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
        worker_id = compat.force_ascii(os.environ["PYTEST_XDIST_WORKER"])
    except KeyError:
        n = 0
    else:
        assert worker_id == some.bytes.matching(
            br"gw(\d+)"
        ), "Unrecognized PYTEST_XDIST_WORKER format"
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

    for i in compat.xrange(1, max_attempts + 1):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            log.info("Probing localhost:{0} (attempt {1})...", port, i)
            sock.connect(("localhost", port))
        except socket.error:
            # The first attempt will almost always fail, because the port isn't
            # open yet. But if it keeps failing after that, we want to know why.
            if i > 1:
                log.exception()
            time.sleep(interval)
        else:
            log.info("localhost:{0} is listening - server is up!", port)
            return
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

        If method() raises an exception, it is logged, unless log_errors=False.
        """

        self.method = method
        self.url = url

        self.log_errors = kwargs.pop("log_errors", True)

        self.request = None
        """The underlying requests.Request object.

        Not set until wait_for_response() returns.
        """

        self.exception = None
        """Exception that occurred while performing the request, if any.

        Not set until wait_for_response() returns.
        """

        log.info("{0}", self)

        func = getattr(requests, method)
        self._worker_thread = threading.Thread(
            target=lambda: self._worker(func, *args, **kwargs),
            name=fmt("WebRequest({0})", self),
        )
        self._worker_thread.daemon = True
        self._worker_thread.start()

    def __str__(self):
        return fmt("HTTP {0} {1}", self.method.upper(), self.url)

    def _worker(self, func, *args, **kwargs):
        try:
            self.request = func(self.url, *args, **kwargs)
        except Exception as exc:
            if self.log_errors:
                log.exception("{0} failed:", self)
            self.exception = exc
        else:
            log.info(
                "{0} --> {1} {2}",
                self,
                self.request.status_code,
                self.request.reason
            )

    def wait_for_response(self, timeout=None):
        """Blocks until the request completes, and returns self.request.
        """
        if self._worker_thread.is_alive():
            log.info("Waiting for response to {0} ...", self)
            self._worker_thread.join(timeout)

        if self.exception is not None:
            raise self.exception
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
        log.info("Web server expected on {0}", self.url)
        wait_until_port_is_listening(self.port, interval=3)
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        """Sends an HTTP /exit GET request to the server.

        The server is expected to terminate its process while handling that request.
        """
        self.get("/exit", log_errors=False)

    def get(self, path, *args, **kwargs):
        return WebRequest.get(self.url + path, *args, **kwargs)

    def post(self, path, *args, **kwargs):
        return WebRequest.post(self.url + path, *args, **kwargs)
