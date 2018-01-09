# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

__author__ = "Microsoft Corporation <ptvshelp@microsoft.com>"
__version__ = "4.0.0a1"


if __name__ == '__main__':
    # XXX Convert side-effects into explicit calls.
    import ptvsd.wrapper
    import pydevd
    pydevd.main()
