# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import os


log_dir = os.getenv("PTVSD_LOG_DIR")
"""If not None, debugger logs its activity to a file named ptvsd-<pid>.log in
the specified directory, where <pid> is the return value of os.getpid().
"""
