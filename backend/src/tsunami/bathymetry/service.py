"""Unified bathymetry data service.

Provides ocean depth data from multiple sources with procedural fallback.
GEBCO/ETOPO integration is a future enhancement — currently uses procedural
generation which is sufficient for demos and testing.
"""

from pathlib import Path
import numpy as np

from tsunami.simulation.grid import Grid
from tsunami.bathymetry.procedural import generate_procedural_bathymetry


class BathymetryService:
    def __init__(self, cache_dir: str = "/tmp/tsunami_bathy"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def check_availability(
        self, lat_min: float, lat_max: float, lon_min: float, lon_max: float,
    ) -> dict[str, bool]:
        """Check which bathymetry sources are available for the given bounds."""
        return {
            "gebco": False,  # Not yet implemented
            "etopo": False,  # Not yet implemented
            "procedural": True,
        }

    def get_bathymetry(
        self, grid: Grid, source: str = "procedural",
    ) -> np.ndarray:
        """Fetch bathymetry data for the given grid.

        Args:
            grid: Target grid to fill with depth values.
            source: Data source — "gebco", "etopo", or "procedural".

        Returns:
            2D array of ocean depth values (positive = below sea level).
        """
        if source == "procedural":
            return self._get_procedural(grid)
        raise ValueError(f"Unknown bathymetry source: {source}. Available: procedural")

    def _get_procedural(self, grid: Grid) -> np.ndarray:
        """Generate procedural bathymetry for the grid."""
        result_grid = generate_procedural_bathymetry(grid)
        return result_grid.depth
