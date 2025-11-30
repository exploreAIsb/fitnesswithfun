from __future__ import annotations

import argparse

from db import init_db


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize the SQLite database.")
    parser.add_argument(
        "--drop",
        action="store_true",
        help="Drop the users table before recreating it.",
    )
    args = parser.parse_args()

    init_db(drop_existing=args.drop)
    print("Database initialized.")


if __name__ == "__main__":
    main()

