"""Enables `python -m envdoctor`."""
try:
    from .envdoctor import main
except ImportError:  # 直接运行 __main__.py 时的兜底
    from envdoctor import main

if __name__ == "__main__":
    raise SystemExit(main())
