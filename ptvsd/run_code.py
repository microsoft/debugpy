# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

# This module is used to implement -c support, since pydevd doesn't support
# it directly. So we tell it to run this module instead, and it just does
# exec on the code.

# It is crucial that this module does *not* do "from __future__ import ...",
# because we want exec below to use the defaults as defined by the flags that
# were passed to the Python interpreter when it was launched.

if __name__ == '__main__':
    from ptvsd.options import code
    exec(code, {})
