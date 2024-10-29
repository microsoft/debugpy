#!/usr/bin/env python

# pyright: strict

import argparse
import os
import shlex
import subprocess
import sys
from contextlib import contextmanager
from typing import Iterator

_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

os.chdir(_SCRIPT_DIR)

_GIT_SUBREPO_ROOT = os.path.join(_SCRIPT_DIR, "build", "git-subrepo")
os.environ["GIT_SUBREPO_ROOT"] = _GIT_SUBREPO_ROOT
os.environ["PATH"] = (
    os.path.join(_GIT_SUBREPO_ROOT, "lib") + os.pathsep + os.environ["PATH"]
)
os.environ["FILTER_BRANCH_SQUELCH_WARNING"] = "1"

_GIT_URL = "https://github.com/fabioz/PyDev.Debugger.git"
_SUBREPO_NAME = "src/debugpy/_vendored/pydevd"
_SUBREPO_TMP = ".git/tmp/subrepo/" + _SUBREPO_NAME


@contextmanager
def cwd(p: str) -> Iterator[None]:
    old = os.getcwd()
    os.chdir(p)
    try:
        yield
    finally:
        os.chdir(old)


def invoke_call(*args: str) -> None:
    print(f"== {shlex.join(args)} ==")
    subprocess.check_call(args)


def invoke_call_ok(*args: str) -> bool:
    try:
        subprocess.check_call(args)
        return True
    except:
        return False


def invoke_output(*args: str, no_log: bool = False) -> str:
    if not no_log:
        print(f"== {shlex.join(args)} ==")

    return subprocess.check_output(args, text=True)


def get_current_commit() -> str:
    return invoke_output(
        "git",
        "config",
        "--file",
        f"{_SUBREPO_NAME}/.gitrepo",
        "subrepo.commit",
        no_log=True,
    ).strip()


def err_exit(message: str):
    print(message, file=sys.stderr)
    sys.exit(1)


def clone() -> None:
    # Clone the repo.
    invoke_call("git", "subrepo", "clone", _GIT_URL, _SUBREPO_NAME)


def reclone() -> None:
    # Remove the temporary branch and worktree.
    invoke_call("git", "subrepo", "clean", _SUBREPO_NAME)
    # Force clone the repo.
    invoke_call("git", "subrepo", "clone", "--force", _GIT_URL, _SUBREPO_NAME)


def pull() -> None:
    # Remove the temporary branch and worktree.
    invoke_call("git", "subrepo", "clean", "--force", _SUBREPO_NAME)

    invoke_call("git", "subrepo", "fetch", _SUBREPO_NAME)
    with cwd(_SUBREPO_NAME):
        new_commit = invoke_output("git", "rev-parse","--verify", "FETCH_HEAD").strip()

    print(f"Updating to pydevd commit {new_commit}.")

    # Pull changes and squash commit them.
    invoke_call("git", "subrepo", "pull", _SUBREPO_NAME)

    # Now, branch to see if there are any diffs. If not, then we can just reclone.
    print("Branching to check if the pydevd tree is clean.")
    invoke_call("git", "subrepo", "clean", _SUBREPO_NAME)
    invoke_call("git", "subrepo", "branch", _SUBREPO_NAME)

    with cwd(_SUBREPO_TMP):
        no_diff = invoke_call_ok("git", "diff", "--quiet", new_commit)

    if no_diff:
        # No diff, so it's safe to manually move the subrepo parent to HEAD.
        print("pydevd tree is clean, moving subrepo parent.")
        new_parent = invoke_output("git", "rev-parse", "HEAD", no_log=True).strip()
        invoke_call(
            "git",
            "config",
            "--file",
            "src/debugpy/_vendored/pydevd/.gitrepo",
            "subrepo.parent",
            new_parent,
        )
        invoke_call("git", "commit", "-am", "Update git-subrepo parent")
    else:
        print("pydevd tree has changes not pushed upstream.")


def branch(message: str) -> None:
    current_commit = get_current_commit()

    # Remove the temporary branch and worktree.
    invoke_call("git", "subrepo", "clean", _SUBREPO_NAME)
    # Ensure we have all of the subrepo refs.
    invoke_call("git", "subrepo", "fetch", _SUBREPO_NAME)
    # Populate the subrepo/src/debugpy/_vendored/pydevd branch with new changes.
    invoke_call("git", "subrepo", "branch", _SUBREPO_NAME)

    # Enter worktree; changes here are applied to the subrepo/src/debugpy/_vendored/pydevd branch.
    with cwd(_SUBREPO_TMP):
        # Remove all commits after the last pull and restage the difference.
        invoke_call("git", "reset", "--soft", current_commit)
        
        hasModifiedFile = invoke_output("git", "status","-s").strip()

        if hasModifiedFile:
            # Commit changes with a new message.
            invoke_call("git", "commit", "-m", message)


def push_to_fork(fork_remote: str, fork_branch: str) -> None:
    invoke_call("git", "push", fork_remote, f"subrepo/src/debugpy/_vendored/pydevd:{fork_branch}")


def commit() -> None:
    invoke_call("git", "subrepo", "commit", _SUBREPO_NAME)


def main() -> None:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    subparsers.add_parser(
        "clone",
        help="clones pydevd for the first time",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers.add_parser(
        "reclone",
        help="force reclones pydevd",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers.add_parser(
        "pull",
        help="pulls pydevd",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    branch_parser = subparsers.add_parser(
        "branch",
        help="squashes changes to pydevd",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    branch_parser.add_argument(
        "-m",
        "--message",
        dest="message",
        required=True,
        help="message for the squashed commit",
    )

    ptf_parser = subparsers.add_parser(
        "push-to-fork",
        help="pushes the squashed changes to pydevd",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ptf_parser.add_argument(
        "--fork-remote",
        dest="fork_remote",
        default="pydevd-fork",
        help="pydevd remote",
    )
    ptf_parser.add_argument(
        "--fork-branch",
        dest="fork_branch",
        required=True,
        help="branch to push to on the remote",
    )

    subparsers.add_parser(
        "commit",
        help=f"runs 'git subrepo commit {_SUBREPO_NAME}'",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    args = parser.parse_args()

    if args.subcommand == "clone":
        clone()
    elif args.subcommand == "reclone":
        reclone()
    elif args.subcommand == "pull":
        pull()
    elif args.subcommand == "branch":
        branch(args.message)
    elif args.subcommand == "push-to-fork":
        push_to_fork(args.fork_remote, args.fork_branch)
    elif args.subcommand == "commit":
        commit()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
