"""Entry point: ``python -m us_places_mcp`` / the ``us-places-mcp`` script."""

from __future__ import annotations

from .server import run


def main() -> None:
    run()


if __name__ == "__main__":
    main()
