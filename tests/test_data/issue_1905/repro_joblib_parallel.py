from joblib import Parallel, delayed


def work() -> int:
    return 42


def main() -> int:
    result = Parallel(n_jobs=4)(delayed(work)() for _ in range(8))
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
