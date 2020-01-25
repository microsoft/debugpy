# For multiproc attach, we need to use a helper stub to import debuggee before running
# Flask; otherwise, we will get the connection only from the subprocess, not from the
# Flask server process.

import debuggee
import runpy

debuggee.setup()
runpy.run_module("flask", run_name="__main__", alter_sys=True)
