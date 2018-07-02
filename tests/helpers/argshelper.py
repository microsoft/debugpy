PROG = 'eggs'
PORT_ARGS = ['--port', '8888']
PYDEVD_DEFAULT_ARGS = ['--qt-support=auto']


def _get_args(*args, **kwargs):
    ptvsd_extras = kwargs.get('ptvsd_extras', [])
    prog = [kwargs.get('prog', PROG)]
    port = kwargs.get('port', PORT_ARGS)
    pydevd_args = kwargs.get('pydevd', PYDEVD_DEFAULT_ARGS)
    return prog + port + ptvsd_extras + pydevd_args + list(args)
