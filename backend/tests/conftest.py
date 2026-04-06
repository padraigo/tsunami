import numpy as np
import pytest


@pytest.fixture
def rng():
    """Seeded random number generator for reproducible tests."""
    return np.random.default_rng(42)


@pytest.fixture
def flat_depth():
    """Uniform ocean depth of 4000m (typical open ocean)."""
    return 4000.0


@pytest.fixture
def gravity():
    """Standard gravitational acceleration."""
    return 9.81
