"""Socket guard for the test suite (CR-J03): any connection or DNS lookup that is not local FAILS and is written to NETGUARD_LOG.

Loaded two ways: tests/conftest.py imports this file in the pytest process, and puts its folder on PYTHONPATH so every Python child process that a
test starts loads it automatically (as `sitecustomize`). Allowed: loopback addresses (127.0.0.0/8, ::1), `localhost`, Unix sockets.
The log is written even when the code under test swallows the exception, so a hidden attempt still fails the run (see conftest).
Switch off only for a deliberate experiment: NETGUARD=off.
"""
import ipaddress
import os
import socket

_LOG = os.environ.get("NETGUARD_LOG")


class NetworkLeak(RuntimeError):
    """A test tried to reach a non-local address."""


def _local(host) -> bool:
    try:
        return ipaddress.ip_address(str(host).split("%")[0].strip("[]")).is_loopback
    except ValueError:
        return str(host).lower() in ("localhost", "")


def _record(kind: str, target) -> None:
    line = f"{os.getpid()} {kind} {target!r}"
    if _LOG:
        with open(_LOG, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    raise NetworkLeak(f"non-local network access blocked by the test socket guard: {line}")


def install() -> None:
    if os.environ.get("NETGUARD") == "off" or getattr(socket, "_netguard_installed", False):
        return
    real_connect, real_connect_ex = socket.socket.connect, socket.socket.connect_ex
    real_getaddrinfo, real_gethostbyname = socket.getaddrinfo, socket.gethostbyname

    def check(sock, address, kind):
        if sock.family == getattr(socket, "AF_UNIX", -1):
            return
        host = address[0] if isinstance(address, tuple) else address
        if not _local(host):
            _record(kind, address)

    def connect(self, address):
        check(self, address, "connect")
        return real_connect(self, address)

    def connect_ex(self, address):
        check(self, address, "connect_ex")
        return real_connect_ex(self, address)

    def getaddrinfo(host, *args, **kwargs):
        if host is not None and not _local(host):
            _record("getaddrinfo", host)
        return real_getaddrinfo(host, *args, **kwargs)

    def gethostbyname(host):
        if not _local(host):
            _record("gethostbyname", host)
        return real_gethostbyname(host)

    socket.socket.connect, socket.socket.connect_ex = connect, connect_ex
    socket.getaddrinfo, socket.gethostbyname = getaddrinfo, gethostbyname
    socket._netguard_installed = True


install()
