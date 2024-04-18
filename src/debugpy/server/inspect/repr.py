# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import functools
import io
from collections.abc import Iterable, Mapping
from typing import Callable
from debugpy.server.inspect import ValueFormat


class ReprTooLongError(Exception):
    pass


class ReprBuilder:
    output: io.StringIO

    format: ValueFormat

    path: list[object]
    """
    Path to the current object being inspected, starting from the root object on which
    repr() was called, with each new element corresponding to a single nest() call.
    """

    chars_remaining: int
    """
    How many more characters are allowed in the output.

    Formatters can use this to optimize by appending larger chunks if there is enough
    space left for them. However, this is just a hint, and formatters aren't required
    to truncate their output - the ReprBuilder will take care of that automatically. 
    """

    def __init__(self, format: ValueFormat):
        self.output = io.StringIO()
        self.format = format
        self.path = []
        self.chars_remaining = self.format.max_length

    def __str__(self) -> str:
        return self.output.getvalue()

    def append_text(self, text: str):
        self.output.write(text)
        self.chars_remaining -= len(text)
        if self.chars_remaining < 0:
            self.output.seek(
                self.format.max_length - len(self.format.truncation_suffix)
            )
            self.output.truncate()
            self.output.write(self.format.truncation_suffix)
            raise ReprTooLongError

    def append_object(self, value: object):
        circular_ref_marker = self.format.circular_ref_marker
        if circular_ref_marker is not None and any(x is value for x in self.path):
            self.append_text(circular_ref_marker)
            return

        formatter = get_formatter(value)
        self.path.append(value)
        try:
            formatter(value, self)
        finally:
            self.path.pop()


def format_object(value: object, builder: ReprBuilder):
    try:
        result = repr(value)
    except BaseException as exc:
        try:
            result = f"<repr() error: {exc}>"
        except:
            result = "<repr() error>"
    builder.append_text(result)


def format_int(value: int, builder: ReprBuilder):
    fs = "{:#x}" if builder.format.hex else "{}"
    text = fs.format(value)
    builder.append_text(text)


def format_iterable(
    value: Iterable, builder: ReprBuilder, *, prefix: str = None, suffix: str = None
):
    if prefix is None:
        prefix = type(value).__name__ + "(("
    builder.append_text(prefix)

    for i, item in enumerate(value):
        if i > 0:
            builder.append_text(", ")
        builder.append_object(item)

    if suffix is None:
        suffix = "))"
    builder.append_text(suffix)


def format_mapping(
    value: Mapping, builder: ReprBuilder, *, prefix: str = None, suffix: str = None
):
    if prefix is None:
        prefix = type(value).__name__ + "(("
    builder.append_text(prefix)

    for i, (key, value) in enumerate(value.items()):
        if i > 0:
            builder.append_text(", ")
        builder.append_object(key)
        builder.append_text(": ")
        builder.append_object(value)

    if suffix is None:
        suffix = "))"
    builder.append_text(suffix)


def format_strlike(
    value: str | bytes | bytearray, builder: ReprBuilder, *, prefix: str, suffix: str
):
    builder.append_text(prefix)

    i = 0
    while i < len(value):
        # Optimistically assume that no escaping will be needed.
        chunk_size = max(1, builder.chars_remaining)
        chunk = repr(value[i : i + chunk_size])
        chunk = chunk[len(prefix) : -len(suffix)]
        builder.append_text(chunk)
        i += chunk_size

    builder.append_text(suffix)


def format_tuple(value: tuple, builder: ReprBuilder):
    suffix = ",)" if len(value) == 1 else ")"
    format_iterable(value, builder, prefix="(", suffix=suffix)


format_str = functools.partial(format_strlike, prefix="'", suffix="'")

format_bytes = functools.partial(format_strlike, prefix="b'", suffix="'")

format_bytearray = functools.partial(format_strlike, prefix="bytearray(b'", suffix="')")

format_list = functools.partial(format_iterable, prefix="[", suffix="]")

format_set = functools.partial(format_iterable, prefix="{", suffix="}")

format_frozenset = functools.partial(format_iterable, prefix="frozenset({", suffix="})")

format_dict = functools.partial(format_mapping, prefix="{", suffix="}")


type Formatter = Callable[[object, ReprBuilder]]

formatters: Mapping[type, Formatter] = {
    int: format_int,
    str: format_str,
    bytes: format_bytes,
    bytearray: format_bytearray,
    tuple: format_tuple,
    list: format_list,
    set: format_set,
    frozenset: format_frozenset,
    dict: format_dict,
}


def get_formatter(value: object) -> Formatter:
    # TODO: proper extensible registry with public API for debugpy plugins.

    # First let's see if we have a formatter for this specific type. Matching on type
    # here must be exact, i.e. no subtypes. The reason for this is that repr must,
    # insofar as possible, reconstitute the original object if eval'd; but if we use
    # a base class repr for a subclass, evaling it will produce instance of that base
    # class instead. This matters when editing variable values, since repr of the value
    # is the text that user will be editing. So if we show a dict repr for a subclass
    # of dict, and user edits it and saves, the value will be silently overwritten with
    # a plain dict. To avoid data loss, we must always use generic repr in cases where
    # we don't know the type exactly.
    formatter = formatters.get(type(value), None)
    if formatter is not None:
        return formatter

    # If there's no specific formatter for this type, pick a generic formatter instead.
    # For this, we do want subtype matching, because those generic formatters produce
    # repr that includes the type name following the standard pattern for those types -
    # so e.g. a Sequence of type T will be formatted as "T((items))".
    match value:
        case Mapping():
            return format_mapping
        case Iterable():
            return format_iterable
        case _:
            return format_object


def formatted_repr(value: object, format: ValueFormat) -> str:
    builder = ReprBuilder(format)
    try:
        builder.append_object(value)
    except ReprTooLongError:
        pass
    except BaseException as exc:
        try:
            builder.append_text(f"<error: {exc}>")
        except:
            builder.append_text("<error>")
    return str(builder)
