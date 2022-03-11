from _pydevd_bundle.pydevd_constants import USE_LIB_COPY, izip

try:
    if USE_LIB_COPY:
        from _pydev_imps._pydev_saved_modules import xmlrpclib
    else:
        import xmlrpclib
except ImportError:
    import xmlrpc.client as xmlrpclib

if USE_LIB_COPY:
    from _pydev_imps._pydev_saved_modules import xmlrpcserver
    SimpleXMLRPCServer = xmlrpcserver.SimpleXMLRPCServer
else:
    from xmlrpc.server import SimpleXMLRPCServer

from io import StringIO

from _pydev_imps._pydev_execfile import execfile

from _pydev_imps._pydev_saved_modules import _queue

from _pydevd_bundle.pydevd_exec2 import Exec

from urllib.parse import quote, quote_plus, unquote_plus  # @UnresolvedImport

