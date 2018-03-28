# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.


__author__ = "Microsoft Corporation <ptvshelp@microsoft.com>"
__version__ = "4.0.0a5"


if __name__ == '__main__':
    # import the wrapper first, so that it gets a chance
    # to detour pydevd socket functionality.
    import ptvsd.wrapper  # noqa
    import pydevd
    pydevd.main()
