import os
import os.path
import unittest
import sys

from . import TEST_ROOT, PROJECT_ROOT
from .__main__ import convert_argv


class ConvertArgsTests(unittest.TestCase):

    def test_no_args(self):
        config, argv, env = convert_argv([])

        self.assertEqual(argv, [
            sys.executable + ' -m unittest',
            'discover',
            '--top-level-directory', PROJECT_ROOT,
            '--start-directory', PROJECT_ROOT,
            ])
        self.assertEqual(env, {
            'HAS_NETWORK': '1',
        })
        self.assertFalse(config.lint_only)
        self.assertFalse(config.lint)

    def test_discovery_full(self):
        config, argv, env = convert_argv([
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
        self.assertFalse(config.lint_only)
        self.assertFalse(config.lint)

    def test_discovery_quick(self):
        config, argv, env = convert_argv([
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
        self.assertFalse(config.lint_only)
        self.assertFalse(config.lint)

    def test_modules(self):
        config, argv, env = convert_argv([
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
        self.assertFalse(config.lint_only)
        self.assertFalse(config.lint)

    def test_no_network(self):
        config, argv, env = convert_argv([
            '--no-network'
            ])

        self.assertEqual(argv, [
            sys.executable + ' -m unittest',
            'discover',
            '--top-level-directory', PROJECT_ROOT,
            '--start-directory', PROJECT_ROOT,
            ])
        self.assertEqual(env, {})
        self.assertFalse(config.lint_only)
        self.assertFalse(config.lint)

    def test_lint(self):
        config, argv, env = convert_argv([
            '-v',
            '--quick',
            '--lint'
            ])

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

        self.assertFalse(config.lint_only)
        self.assertTrue(config.lint)
        self.assertTrue(config.quick)

    def test_lint_only(self):
        config, _, _ = convert_argv([
            '--quick', '--lint-only', '-v',
        ])

        self.assertTrue(config.lint_only)
        self.assertFalse(config.lint)
        self.assertTrue(config.quick)

    def test_coverage(self):
        config, argv, env = convert_argv([
            '--coverage'
            ])

        self.assertEqual(argv, [
            sys.executable + ' -m unittest',
            'discover',
            '--top-level-directory', PROJECT_ROOT,
            '--start-directory', PROJECT_ROOT,
            ])
        self.assertEqual(env, {
            'HAS_NETWORK': '1',
        })
        self.assertFalse(config.lint_only)
        self.assertFalse(config.lint)
        self.assertTrue(config.coverage)

    def test_specify_junit_file(self):
        config, argv, env = convert_argv([
            '--junit-xml=./my-test-file'
        ])

        self.assertEqual(argv, [
            sys.executable + ' -m unittest',
            'discover',
            '--top-level-directory', PROJECT_ROOT,
            '--start-directory', PROJECT_ROOT,
        ])
        self.assertEqual(env, {
            'HAS_NETWORK': '1',
        })
        self.assertFalse(config.lint_only)
        self.assertFalse(config.lint)
        self.assertEqual(config.junit_xml, './my-test-file')
