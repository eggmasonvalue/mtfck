import pytest
from unittest.mock import MagicMock
from mtfck.utils import retry_request

def test_retry_success():
    """Test that the function succeeds without retry if no error."""
    mock_func = MagicMock(return_value="success")

    @retry_request(stop_after=3, min_wait=0, max_wait=0)
    def decorated_func():
        return mock_func()

    assert decorated_func() == "success"
    assert mock_func.call_count == 1

def test_retry_on_exception():
    """Test that the function retries on specified exceptions."""
    mock_func = MagicMock(side_effect=[ConnectionError("Fail 1"), ConnectionError("Fail 2"), "success"])

    @retry_request(stop_after=3, min_wait=0, max_wait=0)
    def decorated_func():
        return mock_func()

    assert decorated_func() == "success"
    assert mock_func.call_count == 3

def test_retry_failure():
    """Test that the function raises RetryError (or the last exception) after max attempts."""
    mock_func = MagicMock(side_effect=ConnectionError("Persistent Failure"))

    @retry_request(stop_after=3, min_wait=0, max_wait=0)
    def decorated_func():
        return mock_func()

    with pytest.raises(ConnectionError):
        decorated_func()

    assert mock_func.call_count == 3

def test_no_retry_on_other_exception():
    """Test that the function does not retry on unspecified exceptions."""
    mock_func = MagicMock(side_effect=ValueError("Invalid Value"))

    @retry_request(stop_after=3, min_wait=0, max_wait=0)
    def decorated_func():
        return mock_func()

    with pytest.raises(ValueError):
        decorated_func()

    assert mock_func.call_count == 1
