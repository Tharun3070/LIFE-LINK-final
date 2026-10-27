"""
LifeLink Unified Dataset Import CLI.
File: scripts/import_dataset.py

Usage:
    python scripts/import_dataset.py --dataset-type donors --file path/to/donors.csv
    python scripts/import_dataset.py --dataset-type hospitals --file path/to/hospitals.csv
    python scripts/import_dataset.py --dataset-type blood_banks --file path/to/blood_banks.csv

Options:
    --dry-run          Validate dataset and show summary without writing to the database.
    --allow-updates    Update existing records matching the identifier (protected user accounts are never overwritten).
    --limit N          Process only the first N valid records.
    --tag TAG          Provenance tag identifying the dataset (default: dataset_import).
"""

import sys
import os
import argparse
import json

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.db.session import SessionLocal
from app.services.dataset_importer import dataset_importer


def main():
    parser = argparse.ArgumentParser(description="LifeLink Safe Dataset Importer")
    parser.add_argument(
        "--dataset-type",
        choices=["donors", "hospitals", "blood_banks"],
        required=True,
        help="Type of dataset being imported (donors, hospitals, or blood_banks)",
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Path to the dataset CSV file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate rows and preview results without committing changes to the database",
    )
    parser.add_argument(
        "--allow-updates",
        action="store_true",
        help="Allow updating non-protected existing records",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of valid records to import",
    )
    parser.add_argument(
        "--tag",
        type=str,
        default="dataset_import",
        help="Provenance tag for imported records",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output summary in JSON format",
    )

    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"Error: File '{args.file}' does not exist.", file=sys.stderr)
        sys.exit(1)

    db = SessionLocal()
    try:
        if args.dataset_type == "donors":
            summary = dataset_importer.import_donors(
                csv_path=args.file,
                db=db,
                dry_run=args.dry_run,
                allow_updates=args.allow_updates,
                limit=args.limit,
                provenance_tag=args.tag,
            )
        elif args.dataset_type == "hospitals":
            summary = dataset_importer.import_hospitals(
                csv_path=args.file,
                db=db,
                dry_run=args.dry_run,
                allow_updates=args.allow_updates,
                limit=args.limit,
                provenance_tag=args.tag,
            )
        elif args.dataset_type == "blood_banks":
            summary = dataset_importer.import_blood_banks(
                csv_path=args.file,
                db=db,
                dry_run=args.dry_run,
                allow_updates=args.allow_updates,
                limit=args.limit,
                provenance_tag=args.tag,
            )
        else:
            print(f"Unsupported dataset type: {args.dataset_type}", file=sys.stderr)
            sys.exit(1)

        if args.json:
            print(json.dumps(summary.model_dump(), indent=2))
        else:
            print("\n" + "=" * 60)
            print(f"  LIFELINK DATASET IMPORT SUMMARY ({summary.dataset_type.upper()})")
            print("=" * 60)
            print(f"  CSV Path:                {summary.csv_path}")
            print(f"  Dry Run:                 {'YES (Database untouched)' if summary.dry_run else 'NO (Live database write)'}")
            print(f"  Allow Updates:           {summary.allow_updates}")
            print(f"  Total Rows Processed:    {summary.total_rows_processed}")
            print(f"  Valid Rows:              {summary.valid_rows}")
            print(f"  Invalid Rows:            {summary.invalid_rows}")
            print(f"  New Records Inserted:    {summary.new_records_inserted}")
            print(f"  Existing Records Updated:{summary.existing_records_updated}")
            print(f"  Duplicate Rows Skipped:  {summary.duplicate_rows_skipped}")
            print(f"  Protected Records:       {summary.protected_records_skipped}")
            print(f"  Failed Rows:             {summary.failed_rows}")
            if summary.dataset_type == "donors":
                print(f"  Unique Phone Numbers:    {summary.unique_phone_numbers}")
                print(f"  Repeated Phone Rows:     {summary.repeated_phone_rows}")
            print(f"  Execution Time:          {summary.execution_seconds}s")

            if summary.missing_required_columns:
                print(f"  Missing Columns:         {', '.join(summary.missing_required_columns)}")
            if summary.unexpected_columns:
                print(f"  Unexpected Columns:      {', '.join(summary.unexpected_columns[:5])}")
            if summary.errors:
                print("\n  Sample Validation Errors:")
                for err in summary.errors[:5]:
                    print(f"    - {err}")
            print("=" * 60 + "\n")

        if summary.missing_required_columns or summary.failed_rows > 0:
            sys.exit(1)

    finally:
        db.close()


if __name__ == "__main__":
    main()
