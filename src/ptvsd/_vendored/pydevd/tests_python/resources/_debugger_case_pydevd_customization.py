import sys
import os


def main():
    env = os.environ.copy()
    pythonpath = env.get('PYTHONPATH', '')
    env['PYTHONPATH'] = os.path.dirname(__file__) + os.pathsep + \
        os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

    from _pydevd_bundle.pydevd_constants import HTTP_JSON_PROTOCOL
    from _pydevd_bundle.pydevd_defaults import PydevdCustomization
    PydevdCustomization.DEFAULT_PROTOCOL = HTTP_JSON_PROTOCOL

    import pydevd
    from _pydev_bundle import pydev_log
    pydev_log.debug('Argv received: %s', sys.argv)
    port = int(sys.argv[1])
    print('before pydevd.settrace')
    pydevd.settrace(port=port, patch_multiprocessing=True, suspend=True)
    print('after pydevd.settrace')

    import subprocess
    if '--use-c-switch' in sys.argv:
        p = subprocess.Popen(
            [sys.executable, '-u', '-c', 'import _debugger_case_pydevd_customization;_debugger_case_pydevd_customization.call()'],
            stdout=subprocess.PIPE,
            env=env,
        )
    else:
        p = subprocess.Popen(
            [sys.executable, '-u', '_debugger_case_pydevd_customization.py', '--simple-call'],
            cwd=os.path.dirname(__file__),
            stdout=subprocess.PIPE,
            env=env,
        )

    stdout, stderr = p.communicate()
    assert b'called' in stdout, 'Did not find b"called" in: %s' % (stdout,)
    print('TEST SUCEEDED!')  # break 2 here


def call():
    print("called")  # break 1 here


if __name__ == '__main__':
    if '--simple-call' in sys.argv:
        call()
    else:
        main()
