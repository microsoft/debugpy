

class SchemaFileError(Exception):
    """A schema-file-related operation failed."""


def read_schema(filename, *, _open=open):
    """Return the data (bytes) in the given schema file."""
    try:
        schemafile = _open(filename, 'rb')
    except FileNotFoundError:
        raise SchemaFileError(
                'schema file {!r} not found'.format(filename))
    with schemafile:
        return schemafile.read()
