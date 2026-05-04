from joblib.externals.loky.backend import get_context


def main() -> int:
    manager = get_context().Manager()
    try:
        values = manager.list()
        values.append("ok")
        print(list(values))
        return 0
    finally:
        manager.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
