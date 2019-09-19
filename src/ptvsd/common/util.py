# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import threading
import sys


def evaluate(code, path=__file__, mode="eval"):
    # Setting file path here to avoid breaking here if users have set
    # "break on exception raised" setting. This code can potentially run
    # in user process and is indistinguishable if the path is not set.
    # We use the path internally to skip exception inside the debugger.
    expr = compile(code, path, "eval")
    return eval(expr, {}, sys.modules)


class Observable(object):
    """An object with change notifications."""

    def __init__(self):
        self.observers = []

    def __setattr__(self, name, value):
        try:
            return super(Observable, self).__setattr__(name, value)
        finally:
            for ob in self.observers:
                ob(self, name)
