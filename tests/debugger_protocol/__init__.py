from .. import skip_py2


# The code under the debugger_protocol package isn't used
# by the debugger (it's used by schema-related tools).  So we don't need
# to support Python 2.
skip_py2()
