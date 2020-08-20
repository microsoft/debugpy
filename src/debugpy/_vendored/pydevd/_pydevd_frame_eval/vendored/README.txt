This folder contains vendored dependencies of the debugger.

Right now this means the 'bytecode' library (MIT license).

To update the version remove the bytecode* contents from this folder and then use:

pip install bytecode --target .

or from master (if needed for some early bugfix):

python -m pip install https://github.com/vstinner/bytecode/archive/master.zip --target .

Then run 'pydevd_fix_code.py' to fix the imports on the vendored file, run its tests (to see
if things are still ok) and commit.

Note: commit the egg-info as a note of the license (force if needed).