"""PAIR-01 starting API. Reload is the feature left for the live experiment."""

from cache import ValueCache


class Config:
    def __init__(self, path: str):
        self._cache = ValueCache(path)

    def get(self, key: str) -> str:
        return self._cache.get(key)
