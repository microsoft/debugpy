if __name__ == '__main__':
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))

    # Create a breakpoint in a <string> frame
    import _pydevd_string_breakpoint
    _pydevd_string_breakpoint.exec_breakpoint()

    # Now run the actual entry point
    import empty_file
    print('TEST SUCEEDED')
