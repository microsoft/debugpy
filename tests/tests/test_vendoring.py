# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.


def test_vendoring(pyfile):
    @pyfile
    def import_debugpy():
        import sys

        class Dummy(object):
            __file__ = None

        class Dummy2(object):
            pass

        class Dummy3(object):
            def __getattribute__(self, *args, **kwargs):
                raise AssertionError("Error")

        sys.modules["pydev_dummy"] = Dummy()
        sys.modules["pydev_dummy2"] = Dummy2()
        sys.modules["pydev_dummy3"] = Dummy3()

        sys.modules["_pydev_dummy"] = Dummy()
        sys.modules["_pydev_dummy2"] = Dummy2()
        sys.modules["_pydev_dummy3"] = Dummy3()

        from debugpy._vendored import force_pydevd  # noqa

        print("Properly applied pydevd vendoring.")

    import subprocess
    import sys

    output = subprocess.check_output([sys.executable, "-u", import_debugpy.strpath])
    output = output.decode("utf-8")
    if "Properly applied pydevd vendoring." not in output:
        raise AssertionError(output)
