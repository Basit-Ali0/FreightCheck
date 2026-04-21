"""Allow ``python -m eval`` — prefer ``python -m eval.run`` per spec."""

from eval.run import main

if __name__ == "__main__":
    raise SystemExit(main())
