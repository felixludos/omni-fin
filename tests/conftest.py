"""Shared pytest fixtures for omnifin tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clear_identity_map():
    """Clear global identity maps before and after each test to prevent cross-test contamination."""
    from omnifin.models import clear_global_identity_map
    clear_global_identity_map()
    yield
    clear_global_identity_map()
