# This script is used for building the pydevd binaries
import argparse
import os
import platform

def build_pydevd_binaries(force: bool):
    os.environ["PYDEVD_USE_CYTHON"] = "yes"

    # Attempt to find where Visual Studio is installed if we're running on Windows.
    if os.name == "nt":
        try:
            import vswhere
            install_path = vswhere.get_latest_path(prerelease=True)
            if install_path is not None:
                os.environ["FORCE_PYDEVD_VC_VARS"] = os.path.join(install_path, "VC", "Auxiliary", "Build", "vcvars64.bat")
        except ImportError:
            pass

    # Run the pydevd build command.
    pydevd_root = os.path.join(os.path.dirname(__file__), "src", "debugpy", "_vendored", "pydevd")

    # Run the appropriate batch script to build the binaries if necessary.
    pydevd_attach_to_process_root = os.path.join(pydevd_root, "pydevd_attach_to_process")
    if platform.system() == "Windows":
        if not os.path.exists(os.path.join(pydevd_attach_to_process_root, "attach_amd64.dll")) or force:
            os.system(os.path.join(pydevd_attach_to_process_root, "windows", "compile_windows.bat"))
    elif platform.system() == "Linux":
        if not os.path.exists(os.path.join(pydevd_attach_to_process_root, "attach_linux_amd64.so")) or force:
            os.system(os.path.join(pydevd_attach_to_process_root, "linux_and_mac", "compile_linux.sh"))
    elif platform.system() == "Darwin":
        if not os.path.exists(os.path.join(pydevd_attach_to_process_root, "attach.dylib")) or force:
            os.system(os.path.join(pydevd_attach_to_process_root, "linux_and_mac", "compile_mac.sh"))
    else:
        print("unsupported platform.system(): {}".format(platform.system()))
        exit(1)


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser(description="Build the pydevd binaries.")
    arg_parser.add_argument("--force", action='store_true', help="Force a rebuild")
    args = arg_parser.parse_args()

    build_pydevd_binaries(args.force)
