import sys
import ptvsd

ptvsd.enable_attach((sys.argv[1], sys.argv[2]))
ptvsd.wait_for_attach()


class SomeClass():
    def __init__(self, someVar):
        self.some_var = someVar

    def do_someting(self):
        someVariable = self.some_var
        return someVariable


def someFunction(someVar):
    someVariable = someVar
    return SomeClass(someVariable).do_someting()


someFunction('value')
print('done')
