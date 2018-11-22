import os
import ptvsd
import time
import backchannel


host = os.getenv('PTVSD_TEST_HOST', 'localhost')
port = os.getenv('PTVSD_TEST_PORT', '5678')
ptvsd.enable_attach((host, port))

if os.getenv('PTVSD_WAIT_FOR_ATTACH', None) is not None:
    backchannel.write_json('wait_for_attach')
    ptvsd.wait_for_attach()

if os.getenv('PTVSD_IS_ATTACHED', None) is not None:
    backchannel.write_json('is_attached')
    while not ptvsd.is_attached():
        time.sleep(0.1)

pause_test = True
if os.getenv('PTVSD_BREAK_INTO_DBG', None) is not None:
    backchannel.write_json('break_into_debugger')
    pause_test = False

if pause_test:
    assert backchannel.read_json() == 'pause_test'
    for _ in range(0, 20):
        time.sleep(0.1)
        print('looping')
else:
    ptvsd.break_into_debugger()
    print('done')
