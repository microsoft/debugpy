
def sentinel(name):
    """Return a named value to use as a sentinel."""
    class Sentinel(object):
        def __repr__(self):
            return name

    return Sentinel()


# NOT_SET indicates that an arg was not provided.
NOT_SET = sentinel('NOT_SET')

# ANY is a datatype surrogate indicating that any value is okay.
ANY = sentinel('ANY')

SIMPLE_TYPES = {None, bool, int, str}
