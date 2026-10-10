"""Parsed configuration cache used by the PAIR-01 starting fixture."""


class ValueCache:
    def __init__(self, path: str):
        self._path = path
        values = {}
        with open(path, encoding="utf-8") as source:
            for line in source:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    raise ValueError("expected key=value")
                key, value = line.split("=", 1)
                key = key.strip()
                if not key:
                    raise ValueError("expected a nonempty key")
                values[key] = value.strip()
        self._values = values

    def get(self, key: str) -> str:
        return self._values[key]
