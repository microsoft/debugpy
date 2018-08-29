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
