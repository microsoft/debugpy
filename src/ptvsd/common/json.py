# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

"""Improved JSON serialization.
"""

import json


JsonDecoder = json.JSONDecoder


class JsonEncoder(json.JSONEncoder):
    """Customizable JSON encoder.

    If the object implements __getstate__, then that method is invoked, and its
    result is serialized instead of the object itself.
    """

    def default(self, value):
        try:
            get_state = value.__getstate__
        except AttributeError:
            return super(JsonEncoder, self).default(value)
        else:
            return get_state()


class JsonObject(object):
    """A wrapped Python object that formats itself as JSON when asked for a string
    representation via str() or format().
    """

    json_encoder_factory = JsonEncoder
    """Used by __format__ when format_spec is not empty."""

    json_encoder = json_encoder_factory(indent=4)
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
        passed to self.json_encoder_factory - which defaults to JSONEncoder - and
        then the resulting formatter is used to serialize self.value as a string.

        Example::

            fmt("{0!j} {0!j:indent=4,sort_keys=True}", x)
        """
        if format_spec:
            # At this point, format_spec is a string that looks something like
            # "indent=4,sort_keys=True". What we want is to build a function call
            # from that which looks like:
            #
            #   json_encoder_factory(indent=4,sort_keys=True)
            #
            # which we can then eval() to create our encoder instance.
            make_encoder = "json_encoder_factory(" + format_spec + ")"
            encoder = eval(
                make_encoder, {"json_encoder_factory": self.json_encoder_factory}
            )
        else:
            encoder = self.json_encoder
        return encoder.encode(self.value)
