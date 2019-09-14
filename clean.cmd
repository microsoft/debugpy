@echo off

pushd %~dp0
del /s /q *.pyc
del /s /q *.pyo
for /d /r %%i in (__pycache__.*) do rd "%%i"
popd

pushd %~dp0\src
del /s /q *.pyd
popd

pushd %~dp0\tests
del /s /q *.pyd
popd
