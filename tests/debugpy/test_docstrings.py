# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import inspect

import debugpy
from debugpy.common import log


def test_docstrings():
    for attr in debugpy.__all__:
        log.info("Checking docstring for debugpy.{0}", attr)
        member = getattr(debugpy, attr)

        doc = inspect.getdoc(member)
        assert doc is not None, f"debugpy.{member} doesn't have a docstring"
        for lineno, line in enumerate(doc.split("\n")):
            assert len(line) <= 72
