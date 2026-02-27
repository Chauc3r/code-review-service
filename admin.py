"""
Admin CLI for managing code review service API keys.

Usage:
    python admin.py create <developer_name>
    python admin.py list
    python admin.py enable <api_key>
    python admin.py disable <api_key>
    python admin.py usage
"""

import os
import sys
import uuid
from datetime import datetime, timezone

import boto3

TABLE_NAME = "review-api-keys"
REGION = "eu-west-2"
PROFILE = os.environ.get("AWS_PROFILE", "ZebraWork")

session = boto3.Session(profile_name=PROFILE, region_name=REGION)
dynamodb = session.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)


def create_key(developer_name: str) -> None:
    """Generate a new API key for a developer."""
    api_key = str(uuid.uuid4())
    table.put_item(
        Item={
            "api_key": api_key,
            "developer_name": developer_name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "enabled": True,
            "usage_count": 0,
        }
    )
    print(f"Created API key for {developer_name}:")
    print(f"  {api_key}")
    print()
    print("Give this to the developer. They set it as REVIEW_API_KEY.")


def list_keys() -> None:
    """List all API keys."""
    resp = table.scan()
    items = resp.get("Items", [])
    if not items:
        print("No API keys found.")
        return
    print(f"{'Developer':<20} {'Enabled':<10} {'Uses':<8} {'API Key'}")
    print("-" * 80)
    for item in sorted(items, key=lambda x: x.get("developer_name", "")):
        print(
            f"{item.get('developer_name', '?'):<20} "
            f"{'yes' if item.get('enabled') else 'NO':<10} "
            f"{item.get('usage_count', 0):<8} "
            f"{item['api_key']}"
        )


def set_enabled(api_key: str, enabled: bool) -> None:
    """Enable or disable an API key."""
    table.update_item(
        Key={"api_key": api_key},
        UpdateExpression="SET enabled = :val",
        ExpressionAttributeValues={":val": enabled},
    )
    status = "enabled" if enabled else "disabled"
    print(f"API key {api_key} is now {status}.")


def show_usage() -> None:
    """Show usage counts for all keys."""
    resp = table.scan()
    items = resp.get("Items", [])
    if not items:
        print("No API keys found.")
        return
    total = 0
    print(f"{'Developer':<20} {'Uses':<10} {'Last Created'}")
    print("-" * 60)
    for item in sorted(items, key=lambda x: x.get("usage_count", 0), reverse=True):
        uses = item.get("usage_count", 0)
        total += uses
        print(
            f"{item.get('developer_name', '?'):<20} "
            f"{uses:<10} "
            f"{item.get('created_at', '?')}"
        )
    print(f"\nTotal reviews: {total}")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "create":
        if len(sys.argv) < 3:
            print("Usage: python admin.py create <developer_name>")
            sys.exit(1)
        create_key(sys.argv[2])
    elif command == "list":
        list_keys()
    elif command == "enable":
        if len(sys.argv) < 3:
            print("Usage: python admin.py enable <api_key>")
            sys.exit(1)
        set_enabled(sys.argv[2], True)
    elif command == "disable":
        if len(sys.argv) < 3:
            print("Usage: python admin.py disable <api_key>")
            sys.exit(1)
        set_enabled(sys.argv[2], False)
    elif command == "usage":
        show_usage()
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
