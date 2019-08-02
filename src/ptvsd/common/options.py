# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import os


log_dir = os.getenv("PTVSD_LOG_DIR")
"""If not None, debugger logs its activity to a file named ptvsd-<pid>.log in
the specified directory, where <pid> is the return value of os.getpid().
"""
