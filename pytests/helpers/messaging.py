# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import itertools

from . import print


class JsonMemoryStream(object):
    """Like JsonIOStream, but without serialization, working directly
    with values stored as-is in memory.

    For input, values are read from the supplied sequence or iterator.
    For output, values are appended to the supplied collection.
    """

    def __init__(self, input, output):
        self.input = iter(input)
        self.output = output

    def close(self):
        pass

    def read_json(self):
        try:
            return next(self.input)
        except StopIteration:
            raise EOFError

    def write_json(self, value):
        self.output.append(value)


class LoggingJsonStream(object):
    """Wraps a JsonStream, and logs all values passing through.
    """

    id_iter = itertools.count()

    def __init__(self, stream, id=None):
        self.stream = stream
        self.id = id or next(self.id_iter)

    def close(self):
        self.stream.close()

    def read_json(self):
        value = self.stream.read_json()
        print('%s --> %r' % (self.id, value))
        return value

    def write_json(self, value):
        print('%s <-- %r' % (self.id, value))
        self.stream.write_json(value)


