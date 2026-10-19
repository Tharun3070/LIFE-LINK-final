from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple


class GeospatialServiceInterface(ABC):
    """Abstract interface for Geospatial and Route intelligence."""

    @abstractmethod
    async def calculate_distance_and_eta(
        self, origin: Tuple[float, float], destination: Tuple[float, float]
    ) -> Dict[str, Any]:
        """Calculates road distance (km) and estimated arrival time (minutes)."""
        raise NotImplementedError("Google Maps / Geospatial API is scheduled for Phase 7.")

    @abstractmethod
    async def get_multi_routes(
        self, origin: Tuple[float, float], destination: Tuple[float, float]
    ) -> List[Dict[str, Any]]:
        """Computes alternative route options with traffic congestion analysis."""
        raise NotImplementedError("Google Maps Routes API is scheduled for Phase 7.")
