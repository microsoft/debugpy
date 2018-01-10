

class StubOpener:

    def __init__(self, *files):
        self.files = list(files)
        self.calls = []

    def open(self, *args):
        self.calls.append(args)

        file = self.files.pop(0)
        if file is None:
            raise FileNotFoundError
        return file
