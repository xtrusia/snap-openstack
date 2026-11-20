# SPDX-FileCopyrightText: 2025 - Canonical Ltd
# SPDX-License-Identifier: Apache-2.0

import os
from unittest.mock import patch

import pytest

from sunbeam.core.proxy import (
    add_no_proxy_host,
    patch_process_env,
    should_bypass,
    update_proxy_env,
)


def test_patch_process_env_no_proxies():
    """Test patch_process_env with no proxies provided."""
    with patch.dict(os.environ, {}, clear=True):
        patch_process_env({})
        assert os.environ == {}


def test_patch_process_env_with_proxies():
    """Test patch_process_env with valid proxies."""
    proxies = {
        "HTTP_PROXY": "http://proxy.example.com:8080",
        "HTTPS_PROXY": "https://proxy.example.com:8443",
        "NO_PROXY": "localhost,127.0.0.1",
    }
    with patch.dict(os.environ, {}, clear=True):
        patch_process_env(proxies)
        assert os.environ["http_proxy"] == "http://proxy.example.com:8080"
        assert os.environ["https_proxy"] == "https://proxy.example.com:8443"
        assert os.environ["HTTP_PROXY"] == "http://proxy.example.com:8080"
        assert os.environ["HTTPS_PROXY"] == "https://proxy.example.com:8443"
        assert os.environ["no_proxy"] == "localhost,127.0.0.1"
        assert os.environ["NO_PROXY"] == "localhost,127.0.0.1"


def test_patch_process_env_missing_https_proxy():
    """Test patch_process_env when HTTPS_PROXY is missing."""
    proxies = {
        "HTTP_PROXY": "http://proxy.example.com:8080",
        "NO_PROXY": "localhost,127.0.0.1",
    }
    with patch.dict(os.environ, {}, clear=True):
        patch_process_env(proxies)
        assert os.environ["http_proxy"] == "http://proxy.example.com:8080"
        assert os.environ["https_proxy"] == "http://proxy.example.com:8080"
        assert os.environ["HTTP_PROXY"] == "http://proxy.example.com:8080"
        assert os.environ["HTTPS_PROXY"] == "http://proxy.example.com:8080"
        assert os.environ["no_proxy"] == "localhost,127.0.0.1"
        assert os.environ["NO_PROXY"] == "localhost,127.0.0.1"


def test_patch_process_env_missing_http_proxy():
    """Test patch_process_env when HTTP_PROXY is missing."""
    proxies = {
        "HTTPS_PROXY": "https://proxy.example.com:8443",
        "NO_PROXY": "localhost,127.0.0.1",
    }
    with patch.dict(os.environ, {}, clear=True):
        patch_process_env(proxies)
        assert os.environ["http_proxy"] == "https://proxy.example.com:8443"
        assert os.environ["https_proxy"] == "https://proxy.example.com:8443"
        assert os.environ["HTTP_PROXY"] == "https://proxy.example.com:8443"
        assert os.environ["HTTPS_PROXY"] == "https://proxy.example.com:8443"
        assert os.environ["no_proxy"] == "localhost,127.0.0.1"
        assert os.environ["NO_PROXY"] == "localhost,127.0.0.1"


def test_patch_process_env_no_http_or_https_proxy():
    """Test patch_process_env when neither HTTP_PROXY nor HTTPS_PROXY is provided."""
    proxies = {"NO_PROXY": "localhost,127.0.0.1"}
    with patch.dict(os.environ, {}, clear=True):
        patch_process_env(proxies)
        assert os.environ == {}


def test_update_proxy_env_fills_https_proxy_without_mutating_process_env():
    """A single configured proxy serves HTTP and HTTPS child requests."""
    env = {
        "PATH": "/usr/bin",
        "NO_PROXY": "localhost",
        "no_proxy": "*",
    }
    proxies = {
        "HTTP_PROXY": "http://proxy.example.com:8080",
        "NO_PROXY": "192.0.2.0/24",
    }

    with patch.dict(
        os.environ,
        {
            "HTTP_PROXY": "http://parent-proxy.example.com:3128",
            "HTTPS_PROXY": "http://parent-proxy.example.com:3128",
            "NO_PROXY": "192.168.0.0/16",
            "no_proxy": "192.168.0.0/16",
        },
        clear=True,
    ):
        parent_env = os.environ.copy()
        update_proxy_env(env, proxies, preserve_no_proxy=True)
        assert os.environ == parent_env

    assert env["HTTP_PROXY"] == proxies["HTTP_PROXY"]
    assert env["HTTPS_PROXY"] == proxies["HTTP_PROXY"]
    assert env["http_proxy"] == proxies["HTTP_PROXY"]
    assert env["https_proxy"] == proxies["HTTP_PROXY"]
    assert env["PATH"] == "/usr/bin"
    assert env["NO_PROXY"] == "localhost,192.0.2.0/24"
    assert env["no_proxy"] == "localhost,192.0.2.0/24"


def test_add_no_proxy_host_uses_effective_uppercase_value():
    env = {"NO_PROXY": "localhost", "no_proxy": "*"}

    add_no_proxy_host(env, "10.1.2.3")

    assert env["NO_PROXY"] == "localhost,10.1.2.3"
    assert env["no_proxy"] == "localhost,10.1.2.3"


@pytest.mark.parametrize(
    "no_proxies,endpoint,expected",
    [
        ([], "example.com", False),  # No proxies, should not bypass
        (["example.com"], "example.com", True),  # Exact match
        (["*.example.com"], "sub.example.com", True),  # Wildcard match
        (["192.168.1.0/24"], "192.168.1.5", True),  # IP in subnet
        (["192.168.1.0/24"], "192.168.2.5", False),  # IP not in subnet
        (["example.com"], "other.com", False),  # No match
        (["*.example.com"], "example.com", False),  # Wildcard no match
        (["192.168.1.0/24"], "not-an-ip", False),  # Invalid IP
        (["*example.com"], "myexample.com", True),  # Ends with match
        (["*example.com"], "example.com", True),  # Ends with match exact
        ([".example.com"], "sub.example.com", True),  # Allow all subdomains
        ([".example.com"], "example.com", False),  # Only subdomains allowed
        (["example.com"], "192.168.1.5", False),  # IP not in no_proxy
    ],
)
def test_should_bypass(no_proxies, endpoint, expected):
    assert should_bypass(no_proxies, endpoint) == expected
