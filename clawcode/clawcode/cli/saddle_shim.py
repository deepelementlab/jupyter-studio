"""Console script shim: forwards to ``saddle.cli:main`` when the extra is installed."""

from __future__ import annotations

import sys


def main() -> None:
    try:
        from saddle.cli import main as saddle_main
    except ImportError as e:
        sys.stderr.write(
            "The 'saddle' extra is not installed. From the clawcode directory run:\n"
            '  py -3 -m pip install -e ".[saddle]"\n'
            "Or install the sibling package directly:\n"
            "  py -3 -m pip install -e ..\\saddle\n"
        )
        raise SystemExit(1) from e
    saddle_main()
