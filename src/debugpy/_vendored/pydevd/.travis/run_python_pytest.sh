if [[ "$PYDEVD_USE_CONDA" != "NO" ]]; then
    source activate build_env
fi

if [[ ("$PYDEVD_PYTHON_VERSION" == "2.6" || "$PYDEVD_PYTHON_VERSION" == "2.7") ]]; then
  # pytest-xdist not available for python == 2.6 and timing out without output with 2.7
    python -m pytest -rf --ignore=_pydevd_frame_eval/vendored

else
    # Note: run vendored tests for bytecode in Python 3.
    python -m pytest -n auto -rf

fi