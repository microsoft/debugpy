if __name__ == '__main__':
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))

    # Create a breakpoint in a <string> frame
    exec("breakpoint()")

    # Now run the actual entry point
    import empty_file
    print('TEST SUCEEDED')
