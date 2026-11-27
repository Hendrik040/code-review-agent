"""Shared test helpers for Phase 8 (impact selection)."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sandbox.local import LocalRepo

_GIT = "git -c user.email=t@example.com -c user.name=t"


@contextmanager
def make_name_clash_repo(n_rules: int = 40) -> Iterator[LocalRepo]:
    """A committed repo where one new rule's `match`/`get_new_command`
    share their names with `n_rules` existing rules, so name matching
    explodes the way it did on thefuck#7. Refs: HEAD~1..HEAD."""
    with LocalRepo(prefix="phase8-clash-") as repo:
        repo.upload_bytes(b"", "pkg/__init__.py")
        repo.upload_bytes(b"", "pkg/rules/__init__.py")
        repo.upload_bytes(
            b'def replace_argument(s, a, b):\n    """Swap one argument."""\n'
            b"    return s.replace(a, b)\n",
            "pkg/utils.py",
        )
        for i in range(n_rules):
            repo.upload_bytes(
                (
                    f"def match(command):\n    return 'r{i}' in command\n\n\n"
                    f"def get_new_command(command):\n    return command + ' r{i}'\n"
                    f"\n\ndef check():\n    return match('x') and get_new_command('x')\n"
                ).encode(),
                f"pkg/rules/r{i}.py",
            )
        assert repo.exec(f"git init -q && {_GIT} add -A && {_GIT} commit -qm base", timeout=60).ok
        repo.upload_bytes(
            b"from pkg.utils import replace_argument\n\n\n"
            b"def match(command):\n    return 'php -s' in command\n\n\n"
            b"def get_new_command(command):\n"
            b"    return replace_argument(command, '-s', '-S')\n",
            "pkg/rules/new.py",
        )
        assert repo.exec(f"{_GIT} add -A && {_GIT} commit -qm new", timeout=60).ok
        yield repo


def git(repo: LocalRepo, cmd: str) -> None:
    """Run a git command with a throwaway identity; assert it worked."""
    res = repo.exec(f"{_GIT} {cmd}", timeout=60)
    assert res.ok, res.stderr


class FakeJev:
    """Stands in for typesafe-sdk's client via shared.jev.ask(client=...).
    Answers every question with `probs.get(id, 0.03)`, except ids in
    `drop`; `error` raises; `delay` sleeps before answering."""

    def __init__(self, probs=None, error=None, drop=(), delay=0.0):
        self.probs, self.error, self.drop, self.delay = probs or {}, error, set(drop), delay
        self.calls: list[tuple[dict, dict]] = []

    def system_one(self, state, questions):
        import time
        from types import SimpleNamespace

        self.calls.append((state, questions))
        time.sleep(self.delay)
        if self.error:
            raise self.error
        return SimpleNamespace(nouls={
            q: SimpleNamespace(noul=self.probs.get(q, 0.03))
            for q in questions if q not in self.drop
        })
