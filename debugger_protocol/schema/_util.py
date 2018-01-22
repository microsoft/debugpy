import hashlib
import json
import re
import urllib.request


def open_url(url):
    """Return a file-like object for (binary) reading the given URL."""
    return urllib.request.urlopen(url)


def get_revision(url, *, _open_url=open_url):
    """Return the revision corresponding to the given URL."""
    if url.startswith('https://github.com/'):
        return github_get_revision(url, _open_url=_open_url)
    else:
        return '<unknown>'


def get_checksum(data):
    """Return the MD5 hash for the given data."""
    m = hashlib.md5()
    m.update(data)
    return m.hexdigest()


##################################
# github

GH_RESOURCE_RE = re.compile(r'^https://github.com'
                            r'/(?P<org>[^/]*)'
                            r'/(?P<repo>[^/]*)'
                            r'/(?P<kind>[^/]*)'
                            r'/(?P<rev>[^/]*)'
                            r'/(?P<path>.*)$')


def github_get_revision(url, *, _open_url=open_url):
    """Return the full commit hash corresponding to the given URL."""
    m = GH_RESOURCE_RE.match(url)
    if not m:
        raise ValueError('invalid GitHub resource URL: {!r}'.format(url))
    org, repo, _, ref, path = m.groups()

    revurl = ('https://api.github.com/repos/{}/{}/commits?sha={}&path={}'
              ).format(org, repo, ref, path)
    with _open_url(revurl) as revinfo:
        raw = revinfo.read()
    data = json.loads(raw.decode())
    return data[0]['sha']


def github_url_replace_ref(url, newref):
    """Return a new URL with the ref replaced."""
    m = GH_RESOURCE_RE.match(url)
    if not m:
        raise ValueError('invalid GitHub resource URL: {!r}'.format(url))
    org, repo, kind, _, path = m.groups()
    parts = (org, repo, kind, newref, path)
    return 'https://github.com/{}/{}/{}/{}/{}'.format(*parts)
