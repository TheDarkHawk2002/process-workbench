"""Compatibility entry point for running the project directly from its checkout."""

from process_workbench.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
