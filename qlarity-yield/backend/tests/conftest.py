# conftest.py — shared pytest fixtures and configuration for the Qlarity test suite.
#
# asyncio_mode = "auto" is set here so all async test functions in any module
# are automatically treated as asyncio coroutines without needing
# @pytest.mark.asyncio on every function.
#
# This is equivalent to passing --asyncio-mode=auto on the CLI, but persisted.

import pytest


def pytest_configure(config):
    """Register custom markers to suppress PytestUnknownMarkWarning."""
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (run with FAST_TESTS=0 or omit FAST_TESTS)",
    )
