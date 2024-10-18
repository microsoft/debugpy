def exec_breakpoint():
    # This exists so we can test that string frames from pydevd
    # don't get handled
    exec("breakpoint()")