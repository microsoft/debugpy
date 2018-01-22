import urllib.error


class StubOpener:

    def __init__(self, *files):
        self.files = list(files)
        self.calls = []

    def open(self, *args):
        self.calls.append(args)

        file = self.files.pop(0)
        if file is None:
            if args[0].startswith('http'):
                raise urllib.error.HTTPError(args[0], 404, 'Not Found',
                                             None, None)
            else:
                raise FileNotFoundError
        return file
