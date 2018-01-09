import os
import os.path
import unittest
import sys

from .__main__ import convert_argv


PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))


class ConvertArgsTests(unittest.TestCase):

    def test_discovery(self):
        argv = convert_argv(['-v', '--failfast'])

        self.assertEqual(argv, [
            sys.executable + ' -m unittest',
            'discover',
            '--start-directory', PROJECT_ROOT,
            '-v', '--failfast',
            ])

    def test_modules(self):
        argv = convert_argv(['-v', '--failfast',
                             'w',
                             'x/y.py:Spam.test_spam'.replace('/', os.sep),
                             'z:Eggs',
                             ])

        self.assertEqual(argv, [
            sys.executable + ' -m unittest',
            '-v', '--failfast',
            'w',
            'x.y.Spam.test_spam',
            'z.Eggs',
            ])

    def test_no_args(self):
        argv = convert_argv([])

        self.assertEqual(argv, [
            sys.executable + ' -m unittest',
            'discover',
            '--start-directory', PROJECT_ROOT,
            ])
