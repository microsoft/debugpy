import os
import os.path
import unittest
import sys

from . import TEST_ROOT, PROJECT_ROOT
from .__main__ import convert_argv


class ConvertArgsTests(unittest.TestCase):

    def test_no_args(self):
        argv, env, runtests, lint = convert_argv([])

        self.assertEqual(argv, [
            sys.executable + ' -m unittest',
            'discover',
            '--top-level-directory', PROJECT_ROOT,
            '--start-directory', PROJECT_ROOT,
            ])
        self.assertEqual(env, {
            'HAS_NETWORK': '1',
        })
        self.assertTrue(runtests)
        self.assertFalse(lint)

    def test_discovery_full(self):
        argv, env, runtests, lint = convert_argv([
            '-v', '--failfast', '--full',
        ])

        self.assertEqual(argv, [
            sys.executable + ' -m unittest',
            'discover',
            '--top-level-directory', PROJECT_ROOT,
            '--start-directory', PROJECT_ROOT,
            '-v', '--failfast',
            ])
        self.assertEqual(env, {
            'HAS_NETWORK': '1',
        })
        self.assertTrue(runtests)
        self.assertFalse(lint)

    def test_discovery_quick(self):
        argv, env, runtests, lint = convert_argv([
            '-v', '--failfast', '--quick',
        ])

        self.assertEqual(argv, [
            sys.executable + ' -m unittest',
            'discover',
            '--top-level-directory', PROJECT_ROOT,
            '--start-directory', os.path.join(TEST_ROOT, 'ptvsd'),
            '-v', '--failfast',
            ])
        self.assertEqual(env, {
            'HAS_NETWORK': '1',
        })
        self.assertTrue(runtests)
        self.assertFalse(lint)

    def test_modules(self):
        argv, env, runtests, lint = convert_argv([
            '-v', '--failfast',
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
        self.assertEqual(env, {
            'HAS_NETWORK': '1',
        })
        self.assertTrue(runtests)
        self.assertFalse(lint)

    def test_no_network(self):
        argv, env, runtests, lint = convert_argv(['--no-network'])

        self.assertEqual(argv, [
            sys.executable + ' -m unittest',
            'discover',
            '--top-level-directory', PROJECT_ROOT,
            '--start-directory', PROJECT_ROOT,
            ])
        self.assertEqual(env, {})
        self.assertTrue(runtests)
        self.assertFalse(lint)

    def test_lint(self):
        argv, env, runtests, lint = convert_argv(['-v', '--quick', '--lint'])

        self.assertEqual(argv, [
            sys.executable + ' -m unittest',
            'discover',
            '--top-level-directory', PROJECT_ROOT,
            '--start-directory', os.path.join(TEST_ROOT, 'ptvsd'),
            '-v',
            ])
        self.assertEqual(env, {
            'HAS_NETWORK': '1',
        })
        self.assertTrue(runtests)
        self.assertTrue(lint)

    def test_lint_only(self):
        argv, env, runtests, lint = convert_argv([
            '--quick', '--lint-only', '-v',
        ])

        self.assertIsNone(argv)
        self.assertIsNone(env)
        self.assertFalse(runtests)
        self.assertTrue(lint)

    def test_coverage(self):
        argv, env, runtests, lint = convert_argv(['--coverage'])

        self.assertEqual(argv, [
            sys.executable + ' -m unittest',
            'discover',
            '--top-level-directory', PROJECT_ROOT,
            '--start-directory', PROJECT_ROOT,
            ])
        self.assertEqual(env, {
            'HAS_NETWORK': '1',
        })
        self.assertEqual(runtests, 'coverage')
        self.assertFalse(lint)
