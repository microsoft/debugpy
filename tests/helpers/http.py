from __future__ import absolute_import

try:
    from http.server import BaseHTTPRequestHandler, HTTPServer
except ImportError:
    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
import threading


class Server:
    """Wraps an http.server.HTTPServer in a thread."""

    def __init__(self, handler, host='', port=8000):
        self.handler = handler
        self._addr = (host, port)
        self._server = None
        self._thread = None

    @property
    def address(self):
        host, port = self._addr
        if host == '':
            host = 'localhost'
        return '{}:{}'.format(host, port)

    def start(self):
        if self._server is not None:
            raise RuntimeError('already started')
        self._server = HTTPServer(self._addr, self.handler)
        self._thread = threading.Thread(
                target=lambda: self._server.serve_forever())
        self._thread.start()

    def stop(self):
        if self._server is None:
            raise RuntimeError('not running')
        self._server.shutdown()
        self._thread.join()
        self._server.server_close()
        self._thread = None
        self._server = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()


def json_file_handler(data):
    """Return an HTTP handler that always serves the given JSON bytes."""

    class HTTPHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type', b'application/json')
            self.send_header('Content-Length',
                             str(len(data)).encode('ascii'))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args, **kwargs):
            pass

    return HTTPHandler


def error_handler(code, msg):
    """Return an HTTP handler that always returns the given error code."""

    class HTTPHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_error(code, msg)

        def log_message(self, *args, **kwargs):
            pass

    return HTTPHandler
