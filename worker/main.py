"""Doorface worker entrypoint — run from worker/: python main.py"""

from __future__ import annotations

import sys


def main() -> None:
	"""Run the HTTP server (not implemented until Phase 1)."""
	print("Doorface worker not implemented yet — see WORKLOG.md", file=sys.stderr)
	raise SystemExit(1)


if __name__ == "__main__":
	main()
