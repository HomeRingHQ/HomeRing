"""
seed_blocklist.py
-----------------
Downloads the FTC's robocall/Do Not Call complaint phone numbers and loads
them into the DynamoDB table 'homering-blocklist'.

How it works:
  The FTC publishes a public dataset of phone numbers reported as robocallers
  or Do Not Call violations at:
    https://www.ftc.gov/system/files/ftc_gov/csv/dnc_complaints_last30d.csv

  This script:
    1. Downloads that CSV using urllib (no third-party HTTP library needed).
    2. Parses each row to extract the phone number.
    3. Writes each number to DynamoDB with:
         phone_number : the 10-digit number (string, partition key)
         category     : "ftc-reported"
         active       : True

  Duplicate numbers are silently overwritten (put_item is idempotent here).

  Run this once to seed the table, then schedule it (cron / Lambda) to keep
  the list fresh.

Usage:
  python seed_blocklist.py

AWS credentials must be available via environment variables, ~/.aws/credentials,
or an IAM role attached to the running instance.

Dependencies:
  pip install boto3
"""

import csv
import io
import re
import urllib.request

import boto3

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

FTC_CSV_URL = (
    "https://www.ftc.gov/system/files/ftc_gov/csv/dnc_complaints_last30d.csv"
)

TABLE_NAME   = "homering-blocklist"
AWS_REGION   = "us-east-1"

# DynamoDB field values written for every record
CATEGORY     = "ftc-reported"
ACTIVE       = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_phone(raw: str) -> str | None:
    """
    Strip all non-digit characters and return a 10-digit US number string.
    Returns None if the result is not exactly 10 digits (or 11 with leading 1).
    """
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return digits
    return None


def download_csv(url: str) -> list[dict]:
    """
    Fetch a CSV file from *url* and return a list of row dicts.
    Uses only the standard library (urllib).
    """
    print(f"[FTC] Downloading {url} ...")
    request = urllib.request.Request(url, headers={"User-Agent": "HomeRing/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        raw_bytes = response.read()
    print(f"[FTC] Downloaded {len(raw_bytes):,} bytes.")

    text = raw_bytes.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    print(f"[FTC] Parsed {len(rows):,} rows.")
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def seed_blocklist():
    rows = download_csv(FTC_CSV_URL)

    dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    table    = dynamodb.Table(TABLE_NAME)

    loaded  = 0
    skipped = 0

    # Use a batch writer for efficiency -- boto3 batches PutItem requests in
    # groups of 25 automatically, reducing round-trips to DynamoDB.
    with table.batch_writer() as batch:
        for row in rows:
            # The FTC CSV uses the column header "Phone Number" (may vary
            # across dataset versions -- fall back to common alternatives).
            raw_number = (
                row.get("Phone Number")
                or row.get("phone_number")
                or row.get("PHONE_NUMBER")
                or ""
            ).strip()

            phone = normalize_phone(raw_number)
            if not phone:
                skipped += 1
                continue

            batch.put_item(Item={
                "phone_number": phone,
                "category":     CATEGORY,
                "active":       ACTIVE,
            })
            loaded += 1

    print(f"[DynamoDB] Done. Loaded: {loaded:,}  |  Skipped (bad number): {skipped:,}")


if __name__ == "__main__":
    seed_blocklist()
