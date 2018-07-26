import requests


def get_web_string(path, obj):
    r = requests.get(path)
    content = r.text
    if obj is not None:
        obj['content'] = content
    return content


def get_web_string_no_error(path, obj):
    try:
        return get_web_string(path, obj)
    except Exception:
        pass
