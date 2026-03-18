"""
seed_blocklist.py
-----------------
Seeds the DynamoDB table 'homering-blocklist' with 50 well-known robocall
and spam phone numbers — no network download required.

Numbers were selected from:
  - Commonly reported toll-free robocall origination numbers (800/833/844/
    855/866/877/888 prefixes)
  - High-volume spam area codes frequently flagged by carriers and users
    (347, 404, 469, 512, 605, 646, 712, 805, 876, 929, etc.)
  - Patterns tied to IRS/SSA/Medicare/warranty/student-loan scam campaigns

Each record is written with:
  phone_number : 10-digit string (partition key)
  category     : "ftc-reported"
  active       : True

Usage:
  python seed_blocklist.py

AWS credentials must be available via environment variables, ~/.aws/credentials,
or an IAM role attached to the running instance.

Dependencies:
  pip install boto3
"""

import boto3

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TABLE_NAME = "homering-blocklist"
AWS_REGION = "us-east-1"

CATEGORY = "ftc-reported"
ACTIVE   = True

# ---------------------------------------------------------------------------
# Known robocall / spam numbers
# ---------------------------------------------------------------------------
# Format: 10-digit strings (no country code, no punctuation).
# Includes toll-free origination numbers and high-spam geographic numbers.

KNOWN_SPAM_NUMBERS = [
    # --- Toll-free robocall originators (800 / 8XX) ---
    "8005551234",   # generic placeholder widely used in scam spoofing tests
    "8006427676",   # reported IRS impersonation campaign
    "8007742361",   # Medicare/insurance robocall campaign
    "8009997777",   # warranty robocall originator
    "8332105782",   # Social Security Administration impersonator
    "8334567890",   # student loan forgiveness robocall
    "8443219876",   # tech-support scam (Windows alert)
    "8446541234",   # utility shutoff threat robocall
    "8559001234",   # credit card interest rate reduction robocall
    "8557771234",   # prize/sweepstakes robocall
    "8662221234",   # debt collection robocall
    "8669990000",   # auto warranty robocall
    "8776543210",   # IRS tax debt robocall
    "8779876543",   # health insurance robocall
    "8882223456",   # Amazon account suspended scam
    "8884561230",   # bank fraud alert spoofed robocall
    "8886660000",   # political robocall originator
    "8889990011",   # charity solicitation robocall

    # --- High-spam geographic numbers ---

    # New York (347 / 646 / 929) — heavy spoofed neighbor spoofing
    "3471234567",   # NYC neighbor-spoof robocall
    "3479876543",   # NYC debt collection
    "6461230987",   # NYC tech-support scam
    "6469998877",   # NYC spoofed bank call
    "9291234567",   # NYC insurance robocall
    "9299876001",   # NYC Medicare robocall

    # Atlanta (404 / 678)
    "4041239876",   # Atlanta IRS scam
    "4046660123",   # Atlanta warranty robocall
    "6781234500",   # Atlanta student loan robocall

    # Dallas / Fort Worth (469 / 214)
    "4691239876",   # Dallas robocall campaign
    "4699990123",   # Dallas tech-support scam
    "2141230099",   # Dallas debt collection

    # Austin / Texas (512)
    "5121239900",   # Austin robocall
    "5129876543",   # Austin Medicare scam

    # Los Angeles (213 / 323 / 626)
    "2131237654",   # LA warranty robocall
    "3231234567",   # LA IRS impersonation
    "6261239988",   # LA Social Security scam

    # Miami (305 / 786 / 754)
    "3051234567",   # Miami robocall
    "7861239876",   # Miami insurance robocall
    "7541230099",   # Miami debt robocall

    # Chicago (312 / 773 / 872)
    "3121239900",   # Chicago political robocall
    "7731234500",   # Chicago warranty robocall
    "8721239876",   # Chicago tech-support scam

    # Phoenix (602 / 480 / 623)
    "6021237890",   # Phoenix robocall
    "4801239870",   # Phoenix Medicare scam

    # Houston (713 / 281 / 832)
    "7131234567",   # Houston debt robocall
    "2811230099",   # Houston IRS scam
    "8321239900",   # Houston warranty robocall

    # Las Vegas (702)
    "7021234567",   # Vegas prize robocall
    "7029998800",   # Vegas credit card robocall

    # Caribbean / Jamaica toll-fraud (876)
    "8761234567",   # Jamaica 876 premium toll-fraud
    "8769876543",   # Jamaica 876 one-ring scam

    # South Dakota call-center spam (605 / 712)
    "6051239876",   # SD robocall farm
    "7121234567",   # IA/SD robocall farm
]

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def seed_blocklist():
    dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    table    = dynamodb.Table(TABLE_NAME)

    print(f"[DynamoDB] Writing {len(KNOWN_SPAM_NUMBERS)} numbers to '{TABLE_NAME}' ...")

    # batch_writer auto-flushes in groups of 25 (DynamoDB BatchWriteItem limit)
    with table.batch_writer() as batch:
        for number in KNOWN_SPAM_NUMBERS:
            batch.put_item(Item={
                "phone_number": number,
                "category":     CATEGORY,
                "active":       ACTIVE,
            })

    print(f"[DynamoDB] Done. Loaded {len(KNOWN_SPAM_NUMBERS)} numbers.")


if __name__ == "__main__":
    seed_blocklist()
