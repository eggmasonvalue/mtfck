import argparse
import sys
from mtfck.ingestion import update_to_today

def main():
    """Main CLI entrypoint for the mtfck package."""
    parser = argparse.ArgumentParser(description="MTFCK Database Update CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    update_parser = subparsers.add_parser("update", help="Update the DuckDB database to today")  # noqa: F841

    args = parser.parse_args()

    if args.command == "update":
        print("Starting database update...")
        try:
            update_to_today()
            print("Database update completed successfully.")
        except Exception as e:
            print(f"Error updating database: {e}")
            sys.exit(1)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
