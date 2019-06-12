# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import itertools
import json

from . import print, colors


class JsonMemoryStream(object):
    """Like JsonIOStream, but working directly with values stored in memory.
    Values are round-tripped through JSON serialization.

    For input, values are read from the supplied sequence or iterator.
    For output, values are appended to the supplied collection.
    """

    def __init__(self, input, output):
        self.input = iter(input)
        self.output = output

    def close(self):
        pass

    def read_json(self, decoder=None):
        decoder = decoder if decoder is not None else json.JSONDecoder()
        try:
            value = next(self.input)
        except StopIteration:
            raise EOFError
        return decoder.decode(json.dumps(value))

    def write_json(self, value, encoder=None):
        encoder = encoder if encoder is not None else json.JSONEncoder()
        value = json.loads(encoder.encode(value))
        self.output.append(value)


class LoggingJsonStream(object):
    """Wraps a JsonStream, and logs all values passing through.
    """

    id_iter = itertools.count()

    def __init__(self, stream, id=None):
        self.stream = stream
        self.id = id or next(self.id_iter)
        self.name = self.id

    def close(self):
        self.stream.close()

    def read_json(self, decoder=None):
        value = self.stream.read_json(decoder)
        s = colors.colorize_json(json.dumps(value))
        print('%s%s --> %s%s' % (colors.LIGHT_CYAN, self.id, colors.RESET, s))
        return value

    def write_json(self, value, encoder=None):
        s = colors.colorize_json(json.dumps(value))
        print('%s%s <-- %s%s' % (colors.LIGHT_CYAN, self.id, colors.RESET, s))
        self.stream.write_json(value, encoder)
