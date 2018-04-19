import warnings

from . import check_modules, prefix_matcher, preimport


# Ensure that pydevd is our vendored copy.
_unvendored, _ = check_modules('pydevd',
                               prefix_matcher('pydev', '_pydev'))
if _unvendored:
    _unvendored = sorted(_unvendored.values())
    msg = 'incompatible copy of pydevd already imported'
    #raise ImportError(msg)
    warnings.warn(msg + ':\n {}'.format('\n  '.join(_unvendored)))


# Now make sure all the top-level modules and packages in pydevd are
# loaded.  Any pydevd modules that aren't loaded at this point, will
# be loaded using their parent package's __path__ (i.e. one of the
# following).
preimport('pydevd', [
    '_pydev_bundle',
    '_pydev_imps',
    '_pydev_runfiles',
    '_pydevd_bundle',
    '_pydevd_frame_eval',
    'pydev_ipython',
    'pydevd_concurrency_analyser',
    'pydevd_plugins',
    'pydevd',
])
