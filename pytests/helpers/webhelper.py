# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import threading
import requests
import re
import socket
import time

def get_web_string(path, obj):
    r = requests.get(path)
    content = r.text
    if obj is not None:
        obj.content = content
    return content


def get_web_string_no_error(path, obj):
    try:
        return get_web_string(path, obj)
    except Exception:
        pass


re_link = r"(http(s|)\:\/\/[\w\.]*\:[0-9]{4,6}(\/|))"
def get_url_from_str(s):
    matches = re.findall(re_link, s)
    if matches and matches[0]and matches[0][0].strip():
        return matches[0][0]
    return None


def get_web_content(link, web_result=None, timeout=1):
    class WebResponse(object):
        def __init__(self):
            self.content = None

        def wait_for_response(self, timeout=1):
            self._web_client_thread.join(timeout)
            return self.content

    response = WebResponse()
    response._web_client_thread = threading.Thread(
        target=get_web_string_no_error,
        args=(link, response),
        name='test.webClient'
    )
    response._web_client_thread.start()
    return response


def wait_for_connection(port, interval=1, attempts=10):
    count = 0
    while count < attempts:
        count += 1
        try:
            print('Waiting to connect to port: %s' % port)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(('localhost', port))
            return
        except socket.error:
            pass
        finally:
            sock.close()
        time.sleep(interval)
