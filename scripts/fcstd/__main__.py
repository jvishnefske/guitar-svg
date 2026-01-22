"""Enable running as python -m scripts.fcstd."""

from scripts.fcstd.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
