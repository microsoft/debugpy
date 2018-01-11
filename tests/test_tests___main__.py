import os
import os.path
import unittest
import sys

from .__main__ import convert_argv


TEST_ROOT = os.path.dirname(__file__)
PROJECT_ROOT = os.path.dirname(TEST_ROOT)


class ConvertArgsTests(unittest.TestCase):

    def test_no_args(self):
        argv = convert_argv([])

        self.assertEqual(argv, [
            sys.executable + ' -m unittest',
            'discover',
            '--top-level-directory', PROJECT_ROOT,
            '--start-directory', PROJECT_ROOT,
            ])

    def test_discovery_full(self):
        argv = convert_argv(['-v', '--failfast', '--full'])

        self.assertEqual(argv, [
            sys.executable + ' -m unittest',
            'discover',
            '--top-level-directory', PROJECT_ROOT,
            '--start-directory', PROJECT_ROOT,
            '-v', '--failfast',
            ])

    def test_discovery_quick(self):
        argv = convert_argv(['-v', '--failfast', '--quick'])

        self.assertEqual(argv, [
            sys.executable + ' -m unittest',
            'discover',
            '--top-level-directory', PROJECT_ROOT,
            '--start-directory', os.path.join(TEST_ROOT, 'ptvsd'),
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
