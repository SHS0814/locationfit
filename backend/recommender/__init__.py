"""Backend-owned service boundary for the existing recommendation engine.

The proven analysis package remains in ``src`` so existing notebooks and batch scripts keep
working. HTTP code imports through this module, which is the only engine boundary exposed to
the backend application.
"""

from src.models.area_recommender import AreaRecommender, RecommendationRequest

__all__ = ["AreaRecommender", "RecommendationRequest"]
