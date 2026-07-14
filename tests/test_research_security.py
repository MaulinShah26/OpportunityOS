import pytest

from opportunityos.infrastructure.research import _assert_public_url


def test_blocks_loopback_url() -> None:
    with pytest.raises(ValueError):
        _assert_public_url("http://127.0.0.1:8000/internal")


def test_blocks_non_http_url() -> None:
    with pytest.raises(ValueError):
        _assert_public_url("file:///etc/passwd")
