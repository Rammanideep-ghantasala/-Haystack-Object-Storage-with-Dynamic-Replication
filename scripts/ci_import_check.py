#!/usr/bin/env python3
import importlib
import os
import pathlib
import sys


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: ci_import_check.py <service-app-dir>", file=sys.stderr)
        return 2

    app_dir = pathlib.Path(sys.argv[1]).resolve()
    if not app_dir.is_dir():
        print(f"app directory not found: {app_dir}", file=sys.stderr)
        return 2

    os.chdir(app_dir)
    sys.path.insert(0, str(app_dir))

    for source in sorted(app_dir.glob("*.py")):
        importlib.import_module(source.stem)

    print(f"Imported all modules in {app_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
