# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

"""Provides a custom string.Formatter with JSON support.

The formatter object is directly exposed as a module, such that all its members
can be invoked directly after it has been imported::

    from ptvsd.common import fmt
    fmt("{0} is {value}", name, value=x)
"""

import json
import string
import sys
import types


class JsonObject(object):
    """A wrapped Python object that formats itself as JSON when asked for a string
    representation via str() or format().
    """

    json_encoder_type = json.JSONEncoder
    """Used by __format__ when format_spec is not empty."""

    json_encoder = json_encoder_type(indent=4)
    """The default encoder used by __format__ when format_spec is empty."""

    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return repr(self.value)

    def __str__(self):
        return format(self)

    def __format__(self, format_spec):
        """If format_spec is empty, uses self.json_encoder to serialize self.value
        as a string. Otherwise, format_spec is treated as an argument list to be
        passed to self.json_encoder_type - which defaults to JSONEncoder - and then
        the resulting formatter is used to serialize self.value as a string.

        Example::

            fmt("{0!j} {0!j:indent=4,sort_keys=True}", x)
        """
        if format_spec:
            # At this point, format_spec is a string that looks something like
            # "indent=4,sort_keys=True". What we want is to build a function call
            # from that which looks like:
            #
            #   json_encoder_type(indent=4,sort_keys=True)
            #
            # which we can then eval() to create our encoder instance.
            make_encoder = "json_encoder_type(" + format_spec + ")"
            encoder = eval(make_encoder, {"json_encoder_type": self.json_encoder_type})
        else:
            encoder = self.json_encoder
        return encoder.encode(self.value)


class Formatter(string.Formatter, types.ModuleType):
    """A custom string.Formatter with support for JSON pretty-printing.

    Adds {!j} format specification. When used, the corresponding value is converted
    to string using json_encoder.encode().

    Since string.Formatter in Python <3.4 does not support unnumbered placeholders,
    they must always be numbered explicitly - "{0} {1}" rather than "{} {}". Named
    placeholders are supported.
    """

    # Because globals() go away after the module object substitution, all method bodies
    # below must access globals via self instead, or re-import modules locally.

    def __init__(self):
        # Set self up as a proper module, and copy globals.
        # types must be re-imported, because globals aren't there yet at this point.
        import types
        types.ModuleType.__init__(self, __name__)
        self.__dict__.update(sys.modules[__name__].__dict__)

    def __call__(self, format_string, *args, **kwargs):
        """Same as self.format().
        """
        return self.format(format_string, *args, **kwargs)

    def convert_field(self, value, conversion):
        if conversion == "j":
            return self.JsonObject(value)
        return super(self.Formatter, self).convert_field(value, conversion)


# Replace the standard module object for this module with a Formatter instance.
sys.modules[__name__] = Formatter()
