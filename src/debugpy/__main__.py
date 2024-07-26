# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import sys
import os

if __name__ == "__main__":

    # There are three ways to run debugpy:
    #
    # 1. Installed as a module in the current environment (python -m debugpy ...)
    # 2. Run as a script from source code (python <repo_root>/src/debugpy ...)
    # 3. Installed as a module in a random directory
    #
    # -----
    #
    # In the first case, no extra work is needed. Importing debugpy will work as expected.
    # Also, running 'debugpy' instead of 'python -m debugpy' will work because of the entry point
    # defined in setup.py.
    #
    # -----
    #
    # In the second case, sys.path[0] is the one added automatically by Python for the directory 
    # containing this file. 'import debugpy' will not work since we need the parent directory 
    # of debugpy/ to be in sys.path, rather than debugpy/ itself. So we need to modify sys.path[0].
    # Running 'debugpy' will not work because the entry point is not defined in this case.
    #
    # -----
    #
    # In the third case, running 'python -m debugpy' will not work because the module is not installed
    # in any environment. Running 'python <path_to_debugpy>' will work, just like the second case. 
    # But running 'debugpy' will not work because even though the entry point is defined, 
    # that path is not in sys.path, so 'import debugpy' will fail. So just like in the second case, 
    # we need to modify sys.path[0].
    #
    # -----
    #
    # If we modify sys.path, 'import debugpy' will work, but it will break other imports
    # because they will be resolved relative to debugpy/ - e.g. `import debugger` will try
    # to import debugpy/debugger.py.
    #
    # To fix both problems, we need to do the following steps:
    # 1. Modify sys.path[0] to point at the parent directory of debugpy/ instead of debugpy/ itself.
    # 2. Import debugpy.
    # 3. Remove sys.path[0] so that it doesn't affect future imports. 
    # 
    # For example, suppose the user did:
    #
    #   python /foo/bar/debugpy ...
    #
    # At the beginning of this script, sys.path[0] will contain "/foo/bar/debugpy".
    # We want to replace it with "/foo/bar', then 'import debugpy', then remove the replaced entry.
    # The imported debugpy module will remain in sys.modules, and thus all future imports of it 
    # or its submodules will resolve accordingly.
    if "debugpy" not in sys.modules:

        # if the user has specified a path to the debugpy module, replace sys.path[0] with
        # the specified path. Otherwise, replace sys.path[0] with the parent directory of debugpy/
        debugpy_path = os.environ.get("DEBUGPY_PATH")
        if (debugpy_path is not None):    
            sys.path[0] = debugpy_path
        else:
            # Do not use dirname() to walk up - this can be a relative path, e.g. ".".
            sys.path[0] = sys.path[0] + "/../"
        
        import debugpy  # noqa
        del sys.path[0]

    from debugpy.server import cli

    cli.main()
