import os

def import_and_enable_debugger():
    if os.getenv('PTVSD_ENABLE_ATTACH', False):
        import ptvsd
        host = os.getenv('PTVSD_TEST_HOST', 'localhost')
        port = os.getenv('PTVSD_TEST_PORT', '5678')
        ptvsd.enable_attach((host, port))
        ptvsd.wait_for_attach()
