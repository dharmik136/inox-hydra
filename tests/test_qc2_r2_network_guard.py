"""
The test suite never leaves this machine.

conftest.py refuses every non-loopback connection and name lookup for the whole
session, and fails a test that tried one even when the code under test caught
the refusal. These tests prove both halves, then forget the attempts they made
on purpose so the per-test check does not fail them.
"""

import socket
import sys

import pytest


def _forget_attempts(before):
    del sys.modules["conftest"]._refused_hosts[before:]


def test_outbound_connection_is_refused():
    guard = sys.modules["conftest"]
    before = len(guard._refused_hosts)
    try:
        with pytest.raises(ConnectionRefusedError):
            socket.create_connection(("93.184.216.34", 80), timeout=1)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with pytest.raises(ConnectionRefusedError):
                sock.connect(("93.184.216.34", 443))
            with pytest.raises(ConnectionRefusedError):
                sock.connect_ex(("93.184.216.34", 443))
        finally:
            sock.close()
        assert guard._refused_hosts[before:] == ["93.184.216.34"] * 3
    finally:
        _forget_attempts(before)


def test_name_lookup_is_refused():
    guard = sys.modules["conftest"]
    before = len(guard._refused_hosts)
    try:
        with pytest.raises(socket.gaierror):
            socket.getaddrinfo("image.pollinations.ai", 443)
        assert guard._refused_hosts[before:] == ["image.pollinations.ai"]
    finally:
        _forget_attempts(before)


def test_http_clients_are_refused_too():
    """requests and httpx both resolve through the guarded functions."""
    import httpx
    import requests

    guard = sys.modules["conftest"]
    before = len(guard._refused_hosts)
    try:
        with pytest.raises(requests.exceptions.ConnectionError):
            requests.get("https://example.com/", timeout=2)
        with pytest.raises(httpx.ConnectError):
            httpx.get("https://example.com/", timeout=2)
        assert "example.com" in guard._refused_hosts[before:]
    finally:
        _forget_attempts(before)


def test_loopback_is_allowed():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    try:
        client = socket.create_connection(server.getsockname(), timeout=2)
        client.close()
        assert socket.getaddrinfo("localhost", 80)
    finally:
        server.close()
