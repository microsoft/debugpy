# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import inspect

import ptvsd
from ptvsd.common import log


def test_docstrings():
    for attr in ptvsd.__all__:
        log.info("Checking docstring for ptvsd.{0}", attr)
        member = getattr(ptvsd, attr)

        doc = inspect.getdoc(member)
        for lineno, line in enumerate(doc.split("\n")):
            assert len(line) <= 72
