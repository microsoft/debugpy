# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import sys
import threading
import time
import ptvsd.untangle

from pytests.helpers.pattern import ANY
from ptvsd.wrapper import ModulesManager


class ModulesEventSink(object):
    def __init__(self):
        self.event_data = []
        self._lock = threading.Lock()

    def send_event(self, event, **kwargs):
        with self._lock:
            self.event_data.append({
                'event': event,
                'args': kwargs,
            })


class TestModulesManager(object):
    def test_invalid_module(self):
        sink = ModulesEventSink()
        mgr = ModulesManager(sink)
        assert mgr.add_or_get_from_path('abc.py') is None
        assert 0 == len(sink.event_data)
        assert [] == mgr.get_all()

    def test_valid_new_module(self):
        sink = ModulesEventSink()
        mgr = ModulesManager(sink)

        orig_module = sys.modules['ptvsd.untangle']
        expected_module = ANY.dict_with({
            'id': ANY.int,
            'name': orig_module.__name__,
            'package': orig_module.__package__,
            'path': orig_module.__file__,
            'version': orig_module.__version__,
        })

        assert expected_module == mgr.add_or_get_from_path(ptvsd.untangle.__file__)
        assert 1 == len(sink.event_data)
        assert [expected_module] == mgr.get_all()
        assert sink.event_data == [
            {
                'event': 'module',
                'args': {
                    'reason': 'new',
                    'module': expected_module,
                },
            },
        ]

    def test_get_only_module(self):
        sink = ModulesEventSink()
        mgr = ModulesManager(sink)

        expected_module = ANY.dict_with({
            'id': 1,
            'name': 'abc.xyz',
            'package': 'abc',
            'path': '/abc/xyz.py',
            'version': '1.2.3.4a1',
        })

        mgr.path_to_module_id['/abc/xyz.py'] = 1
        mgr.module_id_to_details[1] = expected_module

        assert expected_module == mgr.add_or_get_from_path('/abc/xyz.py')
        assert 0 == len(sink.event_data)
        assert [expected_module] == mgr.get_all()

    def test_add_multi_thread(self):
        sink = ModulesEventSink()
        self.mgr = ModulesManager(sink)

        orig_module = sys.modules['ptvsd.untangle']
        expected_module = ANY.dict_with({
            'id': ANY.int,
            'name': orig_module.__name__,
            'package': orig_module.__package__,
            'path': orig_module.__file__,
            'version': orig_module.__version__,
        })
        self.path = orig_module.__file__

        def thread_worker(test, expected):
            time.sleep(0.01)
            assert expected_module == test.mgr.add_or_get_from_path(test.path)

        threads = []
        for _ in range(10):
            thread = threading.Thread(target=thread_worker,
                                      args=(self, expected_module))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        assert 1 == len(sink.event_data)
        assert [expected_module] == self.mgr.get_all()
