"""PAIR-01 starting API. Reload is the feature left for the live experiment."""

from cache import ValueCache


class Config:
    def __init__(self, path: str):
        self._path = path
        self._cache = ValueCache(path)

    def get(self, key: str) -> str:
        return self._cache.get(key)

    def reload(self) -> None:
        replacement = ValueCache(self._path)
        self._cache = replacement
