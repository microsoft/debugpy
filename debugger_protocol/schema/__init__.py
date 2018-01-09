
import os.path


DATA_DIR = os.path.dirname(__file__)

UPSTREAM = 'https://github.com/Microsoft/vscode-debugadapter-node/raw/master/debugProtocol.json'  # noqa
VENDORED = os.path.join(DATA_DIR, 'debugProtocol.json')
METADATA = os.path.join(DATA_DIR, 'UPSTREAM')
