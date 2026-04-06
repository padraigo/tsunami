import json
import numpy as np
import pytest
from tsunami.workers.tasks import run_detail_zone_sync


class TestRunDetailZoneSync:
    def test_runs_boussinesq_and_returns_result(self, tmp_path):
        """Test the synchronous core of the detail task."""
        result = run_detail_zone_sync(
            lat_min=-0.5, lat_max=0.5,
            lon_min=-0.5, lon_max=0.5,
            grid_resolution_m=5000.0,  # coarse for speed (5 km)
            duration_seconds=120.0,
            results_dir=str(tmp_path),
        )
        assert result["status"] == "complete"
        assert result["max_runup_m"] is not None
        assert "inundation_geojson" in result
