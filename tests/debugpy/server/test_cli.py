# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import os
import pickle
import pytest
import subprocess
import sys

# This is used for mocking environment variables
# See https://docs.python.org/3/library/unittest.mock-examples.html for more info
from unittest import mock

from debugpy.common import log
from tests.patterns import some


@pytest.fixture
def cli(pyfile):
    @pyfile
    def cli_parser():
        import os
        import pickle
        import sys
        from debugpy.server import cli

        try:
            cli.parse_args()
        except Exception as exc:
            os.write(1, pickle.dumps(exc))
            sys.exit(1)

        # Check that sys.argv has the correct type after parsing - there should be no bytes.
        assert all(isinstance(s, str) for s in sys.argv)

        # We only care about options that correspond to public switches.
        options = {
            name: getattr(cli.options, name)
            for name in [
                "address",
                "config",
                "log_to",
                "log_to_stderr",
                "mode",
                "target",
                "target_kind",
                "wait_for_client",
            ]
        }

        # Serialize the command line args and the options to stdout
        serialized_data = pickle.dumps([sys.argv[1:], options])
        os.write(1, serialized_data)
        # Ensure all data is written before process exits
        sys.stdout.flush()

    def parse(args):
        log.debug("Parsing argv: {0!r}", args)
        try:
            try:
                # Run the CLI parser in a subprocess, and capture its output.
                output = subprocess.check_output(
                    [sys.executable, "-u", cli_parser.strpath] + args,
                    stderr=subprocess.PIPE  # Capture stderr to help with debugging
                )

                # Deserialize the output and return the parsed argv and options.
                try:
                    argv, options = pickle.loads(output)
                except Exception as e:
                    log.debug("Failed to deserialize output: {0}, Output was: {1!r}", e, output)
                    raise
            except subprocess.CalledProcessError as exc:
                log.debug("Process exited with code {0}. Output: {1!r}, Error: {2!r}", 
                         exc.returncode, exc.output, exc.stderr)
                raise pickle.loads(exc.output)
        except EOFError:
            # We may have just been shutting down. If so, return an empty argv and options.
            argv, options = [], {}

        log.debug("Adjusted sys.argv: {0!r}", argv)
        log.debug("Parsed options: {0!r}", options)
        return argv, options

    return parse


# Test a combination of command line switches
@pytest.mark.parametrize("target_kind", ["file", "module", "code"])
@pytest.mark.parametrize("mode", ["listen", "connect"])
@pytest.mark.parametrize("address", ["8888", "localhost:8888"])
@pytest.mark.parametrize("wait_for_client", ["", "wait_for_client"])
@pytest.mark.parametrize("script_args", ["", "script_args"])
def test_targets(cli, target_kind, mode, address, wait_for_client, script_args):
    expected_options = {
        "mode": mode,
        "target_kind": target_kind,
        "wait_for_client": False
    }

    args = ["--" + mode, address]

    host, sep, port = address.partition(":")
    if sep:
        expected_options["address"] = (host, int(port))
    else:
        expected_options["address"] = ("127.0.0.1", int(address))

    if wait_for_client:
        args += ["--wait-for-client"]
        expected_options["wait_for_client"] = True

    if target_kind == "file":
        target = "spam.py"
        args += [target]
    elif target_kind == "module":
        target = "spam"
        args += ["-m", target]
    elif target_kind == "code":
        target = "123"
        args += ["-c", target]
    else:
        pytest.fail(target_kind)
    expected_options["target"] = target

    if script_args:
        script_args = [
            "ham",
            "--listen",
            "--wait-for-client",
            "-y",
            "spam",
            "--",
            "--connect",
            "-c",
            "--something",
            "-m",
        ]
        args += script_args
    else:
        script_args = []

    argv, options = cli(args)
    assert argv == script_args
    assert options == some.dict.containing(expected_options)

@pytest.mark.parametrize("value", [True, False])
def test_configure_subProcess(cli, value):
    args = ["--listen", "8888", "--configure-subProcess", str(value), "spam.py"]
    _, options = cli(args)

    assert options["config"]["subProcess"] == value

@pytest.mark.parametrize("value", [True, False])
def test_configure_subProcess_from_environment(cli, value):
    args = ["--listen", "8888", "spam.py"]
    with mock.patch.dict(os.environ, {"DEBUGPY_EXTRA_ARGV": "--configure-subProcess " + str(value)}):
        _, options = cli(args)

        assert options["config"]["subProcess"] == value

def test_unsupported_switch(cli):
    with pytest.raises(ValueError) as ex:
        cli(["--listen", "8888", "--xyz", "123", "spam.py"])
    
    assert "unrecognized switch --xyz" in str(ex.value)

def test_unsupported_switch_from_environment(cli):
    with pytest.raises(ValueError) as ex:
        with mock.patch.dict(os.environ, {"DEBUGPY_EXTRA_ARGV": "--xyz 123"}):
            cli(["--listen", "8888", "spam.py"])
    
    assert "unrecognized switch --xyz" in str(ex.value)

def test_unsupported_configure(cli):
    with pytest.raises(ValueError) as ex:
        cli(["--connect", "127.0.0.1:8888", "--configure-xyz", "123", "spam.py"])
    
    assert "unknown property 'xyz'" in str(ex.value)

def test_unsupported_configure_from_environment(cli):
    with pytest.raises(ValueError) as ex:
        with mock.patch.dict(os.environ, {"DEBUGPY_EXTRA_ARGV": "--configure-xyz 123"}):
            cli(["--connect", "127.0.0.1:8888", "spam.py"])

    assert "unknown property 'xyz'" in str(ex.value)

def test_address_required(cli):
    with pytest.raises(ValueError) as ex:
        cli(["-m", "spam"])
    
    assert "either --listen or --connect is required" in str(ex.value)

def test_missing_target(cli):
    with pytest.raises(ValueError) as ex:
        cli(["--listen", "8888"])
    
    assert "missing target" in str(ex.value)

def test_duplicate_switch(cli):
    with pytest.raises(ValueError) as ex:
        cli(["--listen", "8888", "--listen", "9999", "spam.py"])
    
    assert "duplicate switch on command line: --listen" in str(ex.value)

def test_duplicate_switch_from_environment(cli):
    with pytest.raises(ValueError) as ex:
        with mock.patch.dict(os.environ, {"DEBUGPY_EXTRA_ARGV": "--listen 8888 --listen 9999"}):
            cli(["spam.py"])
    
    assert "duplicate switch from environment: --listen" in str(ex.value)

# Test that switches can be read from the environment
def test_read_switches_from_environment(cli):
    args = ["spam.py"]

    with mock.patch.dict(os.environ, {"DEBUGPY_EXTRA_ARGV": "--connect 5678"}):
        _, options = cli(args)

        assert options["mode"] == "connect"
        assert options["address"] == ("127.0.0.1", 5678)
        assert options["target"] == "spam.py"

# Test that command line switches override environment variables
def test_override_environment_switch(cli):
    args = ["--connect", "8888", "spam.py"]

    with mock.patch.dict(os.environ, {"DEBUGPY_EXTRA_ARGV": "--connect 5678"}):
        _, options = cli(args)

        assert options["mode"] == "connect"
        assert options["address"] == ("127.0.0.1", 8888)
        assert options["target"] == "spam.py"

# Test that script args (passed to target) are preserved
def test_script_args(cli):
    args = ["--listen", "8888", "spam.py", "arg1", "arg2"]
    argv, options = cli(args)

    assert argv == ["arg1", "arg2"]
    assert options["target"] == "spam.py"
