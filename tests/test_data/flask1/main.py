# For multiproc attach, we need to use a helper stub to import debug_me before running
# Flask; otherwise, we will get the connection only from the subprocess, not from the
# Flask server process.

import debug_me  # noqa
import runpy

runpy.run_module("flask", run_name="__main__")
