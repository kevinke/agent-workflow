class CachedValue:
    def __init__(self, config: dict) -> None:
        self._value = config["value"]

    def read(self) -> int:
        return self._value
