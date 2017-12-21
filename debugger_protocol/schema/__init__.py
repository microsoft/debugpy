
import os.path


DATA_DIR = os.path.dirname(__file__)

UPSTREAM = 'https://raw.githubusercontent.com/Microsoft/vscode-debugadapter-node/master/debugProtocol.json'
VENDORED = os.path.join(DATA_DIR, 'debugProtocol.json')
