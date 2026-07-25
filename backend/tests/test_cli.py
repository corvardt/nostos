"""The launcher: argument shapes, instance detection, and the pid file."""

from __future__ import annotations

import os
import socket

import pytest

from nostos import cli, pidfile


# ------------------------------------------------------------------ arguments


def test_the_bare_command_runs_the_server():
    assert cli.build_parser().parse_args([]).command == "run"


@pytest.mark.parametrize("argv", [["status"], ["--port", "9000", "status"], ["status", "--port", "9000"]])
def test_flags_may_come_before_or_after_the_command(argv):
    """Subparsers would have made one of these an error. Nobody should have to
    know which."""
    args = cli.build_parser().parse_args(argv)
    assert args.command == "status"


def test_an_unknown_command_is_rejected():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["frobnicate"])


def test_version_short_circuits(capsys):
    assert cli.main(["--version"]) == 0
    assert capsys.readouterr().out.strip()


# ------------------------------------------------------------------- the port


def test_a_busy_port_rolls_to_the_next_one():
    """Something else on 8000 is not a reason to refuse to start."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        taken = sock.getsockname()[1]
        assert cli.port_is_free(taken) is False
        assert cli.find_port(taken) == taken + 1


def test_a_free_port_is_used_as_asked():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        free = sock.getsockname()[1]
    assert cli.find_port(free) == free


# --------------------------------------------------------------- is it ours?


def test_nothing_listening_is_not_an_instance():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    assert cli.probe(port, timeout=0.2) is None


def test_a_stranger_on_the_port_is_not_an_instance(monkeypatch):
    """Opening a browser at somebody else's server would be worse than failing."""

    class NotUs:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"status": "grafana"}'

    monkeypatch.setattr(cli.urllib.request, "urlopen", lambda *a, **k: NotUs())
    assert cli.probe(8000) is None


# -------------------------------------------------------------- the pid file


def test_the_pid_file_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(pidfile, "PATH", tmp_path / "nostos.pid")
    pidfile.write()
    assert pidfile.read() == os.getpid()
    pidfile.clear()
    assert pidfile.read() is None


def test_a_pid_file_naming_a_dead_process_is_ignored(tmp_path, monkeypatch):
    """A kill -9 or a power cut leaves one behind; it must not read as running."""
    path = tmp_path / "nostos.pid"
    monkeypatch.setattr(pidfile, "PATH", path)

    # Find a pid that is not in use, rather than trusting a large number to be free.
    dead = 999_999
    while True:
        try:
            os.kill(dead, 0)
        except OSError:
            break
        dead -= 1
    path.write_text(str(dead))

    assert pidfile.read() is None


def test_a_corrupt_pid_file_is_ignored(tmp_path, monkeypatch):
    path = tmp_path / "nostos.pid"
    monkeypatch.setattr(pidfile, "PATH", path)
    path.write_text("not a number")
    assert pidfile.read() is None


def test_stopping_when_nothing_runs_is_not_an_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pidfile, "PATH", tmp_path / "nostos.pid")
    args = cli.build_parser().parse_args(["stop"])
    assert cli.cmd_stop(args) == 0
    assert "not running" in capsys.readouterr().out
