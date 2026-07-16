# Issue #1905 full runtime repro

This folder contains minimal runtime repro scripts for:
- direct loky manager startup
- joblib Parallel worker startup

## Scripts

- `repro_loky_manager.py`
- `repro_joblib_parallel.py`

## Prerequisites

- `joblib` installed in the Python environment used to run debugpy.
- Run from repo root with `PYTHONPATH=src` so `python -m debugpy` uses this checkout.

## Matrix commands (PowerShell)

```powershell
$py = "c:/Users/rchiodo/source/repos/debugpy/.venv/Scripts/python.exe"
$env:PYTHONPATH = "C:/Users/rchiodo/source/repos/debugpy/src"

& $py tests/test_data/issue_1905/repro_loky_manager.py
& $py -m debugpy --listen 127.0.0.1:0 tests/test_data/issue_1905/repro_loky_manager.py
& $py -m debugpy --listen 127.0.0.1:0 --configure-subProcess false tests/test_data/issue_1905/repro_loky_manager.py
& $py -m debugpy --listen 127.0.0.1:0 --configure-subProcess true tests/test_data/issue_1905/repro_loky_manager.py

& $py tests/test_data/issue_1905/repro_joblib_parallel.py
& $py -m debugpy --listen 127.0.0.1:0 tests/test_data/issue_1905/repro_joblib_parallel.py
& $py -m debugpy --listen 127.0.0.1:0 --configure-subProcess false tests/test_data/issue_1905/repro_joblib_parallel.py
& $py -m debugpy --listen 127.0.0.1:0 --configure-subProcess true tests/test_data/issue_1905/repro_joblib_parallel.py

Remove-Item Env:PYTHONPATH
```

## Optional log capture

Set `DEBUGPY_LOG_DIR` before each invocation to collect subprocess patching logs.
Search logs for patching lines and traceback evidence.

## Notes

- On Windows/Python 3.13 in this workspace, the scripts pass in all modes and logs show string argv values for `-c` patching.
- The issue discussion indicates failures on Linux/macOS where some patched argv values may be bytes.
- On affected platforms, compare behavior between default subprocess handling and `--configure-subProcess false`.
