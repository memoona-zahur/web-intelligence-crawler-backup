"""The socket guard itself works (it is what keeps the suite offline). Each check runs in a child process with its own log file."""

import os
import subprocess
import sys
from pathlib import Path

GUARD_DIR = Path(__file__).parent / "netguard"


def run_snippet(code: str, tmp_path: Path):
    log = tmp_path / "guard.log"
    env = dict(os.environ, PYTHONPATH=str(GUARD_DIR), NETGUARD_LOG=str(log))
    env.pop("NETGUARD", None)
    done = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True, env=env, timeout=60)
    return done, (log.read_text().splitlines() if log.exists() else [])


def test_non_local_connection_and_dns_are_blocked_and_logged(tmp_path):
    code = (
        "import socket\n"
        "for call in (lambda: socket.create_connection(('93.184.216.34', 80), timeout=2), lambda: socket.getaddrinfo('example.com', 80),\n"
        "             lambda: socket.gethostbyname('example.org'), lambda: socket.socket().connect(('8.8.8.8', 53))):\n"
        "    try:\n"
        "        call(); print('NOT BLOCKED')\n"
        "    except RuntimeError as e:\n"
        "        print('blocked', type(e).__name__)\n"
    )
    done, log = run_snippet(code, tmp_path)
    assert done.stdout.count("blocked NetworkLeak") == 4 and "NOT BLOCKED" not in done.stdout, done.stdout + done.stderr
    assert len(log) >= 4 and any("example.com" in line for line in log)


def test_an_exception_swallowed_by_the_code_still_leaves_a_log_line(tmp_path):
    code = "import socket\ntry:\n    socket.getaddrinfo('swallowed.example.net', 80)\nexcept Exception:\n    pass\n"
    _done, log = run_snippet(code, tmp_path)
    assert any("swallowed.example.net" in line for line in log)       # conftest turns a non-empty log into a failed run


def test_loopback_and_unix_style_local_access_is_allowed(tmp_path):
    code = (
        "import socket, threading\n"
        "s = socket.socket(); s.bind(('127.0.0.1', 0)); s.listen(1); port = s.getsockname()[1]\n"
        "threading.Thread(target=s.accept, daemon=True).start()\n"
        "c = socket.create_connection(('127.0.0.1', port), timeout=2); print('local ok'); print(len(socket.getaddrinfo('localhost', port)) > 0)\n"
    )
    done, log = run_snippet(code, tmp_path)
    assert "local ok" in done.stdout and log == [], done.stdout + done.stderr


def test_the_suite_runs_with_the_guard_on_in_this_process():
    import socket

    assert getattr(socket, "_netguard_installed", False) is True or os.environ.get("NETGUARD") == "off"
