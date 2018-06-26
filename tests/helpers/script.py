import os.path

from .lock import Lockfile, LockTimeoutError


########################
# labels

class InvalidLabelError(ValueError):
    """A label is not valid."""

    def __init__(self, label):
        msg = 'label {!r} not valid'.format(label)
        super(InvalidLabelError, self).__init__(msg)
        self.label = label


class LabelNotFoundError(RuntimeError):
    """A script label (e.g. "# <spam>") was not found."""

    def __init__(self, label):
        msg = 'label {!r} not found'.format(label)
        super(LabelNotFoundError, self).__init__(msg)
        self.label = label


def check_label(label):
    """Raise InvalidLabelError is the label is not valid."""
    label = str(label)
    if not label:
        raise InvalidLabelError(label)


def iter_until_label(lines, label):
    """Yield (line, found) for each line until the label matches.

    A label is a line that looks like "# <spam>" (leading whitespace
    is ignored).  If the label is not found then LabelNotFoundError
    is raised.

    "lines" should be an iterator of the lines of a script (with or
    without EOL).  It also works with any other iterable (e.g. a list),
    but only iterators preserve position.
    """
    check_label(label)

    expected = '# <{}>'.format(label)
    for line in lines:
        if line.strip() == expected:
            yield line, True
            break
        yield line, False
    else:
        raise LabelNotFoundError(label)


def find_line(script, label):
    """Return the line number (1-based) of the line after the label."""
    lines = iter(script.splitlines())
    # Line numbers start with 1.
    for lineno, _ in enumerate(iter_until_label(lines, label), 1):
        pass
    return lineno + 1  # the line after


########################
# wait points

def insert_release(script, lockfile, label=None):
    """Return (script, wait func) after adding a done script to the original.

    If a label is provided then the done script is inserted just before
    the label.  Otherwise it is added to the end of the script.

    The script will unblock the wait func at the label (or the end).
    """
    if isinstance(lockfile, str):
        lockfile = Lockfile(lockfile)

    donescript, wait = lockfile.wait_for_script()
    if label is None:
        script += donescript
    else:
        leading = []
        lines = iter(script.splitlines())
        for line, matched in iter_until_label(lines, label):
            if matched:
                leading.extend([
                    donescript,
                    line,
                    '',  # Make sure the label is on its own line.
                ])
                break
            leading.append(line)
        # TODO: Use os.linesep?
        script = '\n'.join(leading) + '\n'.join(lines)
    return script, wait


def set_release(filename, lockfile, label=None, script=None):
    """Return (script, wait func) after adding a done script to the original.

    In addition to the functionality of insert_release(), this function
    writes the resulting script to the given file.  If no original
    script is given then it is read from the file.
    """
    if script is None:
        if not os.path.exists(filename):
            raise ValueError(
                'invalid filename {!r} (file missing)'.format(filename))
        with open(filename) as scriptfile:
            script = scriptfile.read()

    script, wait = insert_release(script, lockfile, label)

    with open(filename, 'w') as scriptfile:
        scriptfile.write(script)

    return script, wait


def insert_lock(script, lockfile, label=None, timeout=5):
    """Return (done func, script) after adding a wait script to the original.

    If a label is provided then the wait script is inserted just before
    the label.  Otherwise it is added to the end of the script.

    The script will pause at the label (or the end) until the returned
    "done" func is called or the timeout is reached.
    """
    if isinstance(lockfile, str):
        lockfile = Lockfile(lockfile)

    try:
        done, waitscript = lockfile.wait_in_script(timeout=timeout)
    except LockTimeoutError:
        raise RuntimeError('lock file {!r} already exists'.format(lockfile))

    if label is None:
        script += waitscript
    else:
        leading = []
        lines = iter(script.splitlines())
        for line, matched in iter_until_label(lines, label):
            if matched:
                leading.extend([
                    waitscript,
                    line,
                    '',  # Make sure the label is on its own line.
                ])
                break
            leading.append(line)
        # TODO: Use os.linesep?
        script = '\n'.join(leading) + '\n'.join(lines)
    return done, script


def set_lock(filename, lockfile, label=None, script=None, timeout=5):
    """Return (done func, script) after adding a wait script to the original.

    In addition to the functionality of insert_lock(), this function
    writes the resulting script to the given file.  If no original
    script is given then it is read from the file.
    """
    if script is None:
        if not os.path.exists(filename):
            raise ValueError(
                'invalid filename {!r} (file missing)'.format(filename))
        with open(filename) as scriptfile:
            script = scriptfile.read()

    done, script = insert_lock(script, lockfile, label, timeout)

    with open(filename, 'w') as scriptfile:
        scriptfile.write(script)

    return done, script
