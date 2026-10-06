from service import CachedValue


def main() -> int:
    config = {"value": 1}
    cached = CachedValue(config)
    initial = cached.read()
    config["value"] = 2
    configured = config["value"]
    actual = cached.read()
    print(f"initial={initial}")
    print(f"configured={configured}")
    print(f"actual={actual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
