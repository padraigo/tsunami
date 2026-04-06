"""Unified bathymetry data service.

Provides ocean depth data from multiple sources:
  - gebco: Real GEBCO global grid (~450m resolution)
  - procedural: Generated continental shelf (fallback for testing/demos)
"""

from pathlib import Path
import numpy as np

from tsunami.simulation.grid import Grid
from tsunami.bathymetry.procedural import generate_procedural_bathymetry


class BathymetryService:
    def __init__(self, cache_dir: str = "/tmp/tsunami_bathy"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _find_gebco(self) -> Path | None:
        """Search for a GEBCO NetCDF file in the cache directory."""
        for pattern in ["GEBCO_*.nc", "gebco_*.nc"]:
            files = list(self.cache_dir.glob(pattern))
            if files:
                return files[0]
        return None

    def check_availability(
        self, lat_min: float, lat_max: float, lon_min: float, lon_max: float,
    ) -> dict[str, bool]:
        """Check which bathymetry sources are available for the given bounds."""
        return {
            "gebco": self._find_gebco() is not None,
            "etopo": False,
            "procedural": True,
        }

    def get_bathymetry(
        self, grid: Grid, source: str = "auto",
    ) -> np.ndarray:
        """Fetch bathymetry data for the given grid.

        Args:
            grid: Target grid to fill with depth values.
            source: "auto" (GEBCO if available, else procedural),
                    "gebco", or "procedural".

        Returns:
            2D array of ocean depth values (positive = below sea level).
        """
        if source == "auto":
            gebco_path = self._find_gebco()
            if gebco_path:
                return self._get_gebco(grid, gebco_path)
            return self._get_procedural(grid)

        if source == "gebco":
            gebco_path = self._find_gebco()
            if not gebco_path:
                raise FileNotFoundError(
                    f"No GEBCO file found in {self.cache_dir}. "
                    "Download from https://www.gebco.net/data-products/gridded-bathymetry-data "
                    "and place the .nc file in the bathymetry cache directory."
                )
            return self._get_gebco(grid, gebco_path)

        if source == "procedural":
            return self._get_procedural(grid)

        raise ValueError(f"Unknown bathymetry source: {source}. Available: auto, gebco, procedural")

    def _get_gebco(self, grid: Grid, nc_path: Path) -> np.ndarray:
        """Load and resample GEBCO data for the grid."""
        from tsunami.bathymetry.gebco import load_gebco
        return load_gebco(nc_path, grid)

    def _get_procedural(self, grid: Grid) -> np.ndarray:
        """Generate procedural bathymetry for the grid."""
        result_grid = generate_procedural_bathymetry(grid)
        return result_grid.depth
