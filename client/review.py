#!/usr/bin/env python3
"""
Code review client — sends git diff to the review Lambda and prints results.

Environment variables:
    REVIEW_API_KEY  — Your personal API key
    REVIEW_URL      — Lambda Function URL endpoint
"""

import json
import os
import subprocess
import sys


def get_diff() -> str:
    """Get staged diff, falling back to unstaged diff."""
    result = subprocess.run(
        ["git", "diff", "--staged"],
        capture_output=True,
        text=True,
    )
    diff = result.stdout.strip()
    if diff:
        return diff

    result = subprocess.run(
        ["git", "diff"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def print_colored(text: str, color: str) -> None:
    """Print with ANSI color codes."""
    colors = {
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "bold": "\033[1m",
        "dim": "\033[2m",
        "reset": "\033[0m",
    }
    print(f"{colors.get(color, '')}{text}{colors['reset']}")


def main() -> int:
    api_key = os.environ.get("REVIEW_API_KEY")
    review_url = os.environ.get("REVIEW_URL")

    if not api_key:
        print_colored("Error: REVIEW_API_KEY environment variable not set.", "red")
        return 1
    if not review_url:
        print_colored("Error: REVIEW_URL environment variable not set.", "red")
        return 1

    diff = get_diff()
    if not diff:
        print_colored("No changes to review (no staged or unstaged diff).", "yellow")
        return 0

    print_colored("Sending diff for review...", "blue")
    print(f"  Diff size: {len(diff):,} characters")
    print()

    try:
        import requests
    except ImportError:
        # Fall back to urllib if requests not installed
        import urllib.request
        import urllib.error

        req = urllib.request.Request(
            review_url,
            data=diff.encode("utf-8"),
            headers={
                "Content-Type": "text/plain",
                "x-api-key": api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            print_colored(f"HTTP {e.code}: {body}", "red")
            return 1
    else:
        resp = requests.post(
            review_url,
            headers={
                "Content-Type": "text/plain",
                "x-api-key": api_key,
            },
            data=diff.encode("utf-8"),
            timeout=300,
        )
        if resp.status_code != 200:
            print_colored(f"HTTP {resp.status_code}: {resp.text}", "red")
            return 1
        data = resp.json()

    # Print results
    print()
    if data["verdict"] == "PASS":
        print_colored("  ╔═══════════════╗", "green")
        print_colored("  ║   PASS  ✅    ║", "green")
        print_colored("  ╚═══════════════╝", "green")
    else:
        print_colored("  ╔═══════════════╗", "red")
        print_colored("  ║   FAIL  ❌    ║", "red")
        print_colored("  ╚═══════════════╝", "red")

    print()
    print_colored(f"  Vote: {data['vote_breakdown']}", "bold")
    if data.get("warning"):
        print_colored(f"  Warning: {data['warning']}", "yellow")
    print()

    # Per-model verdicts
    print_colored("  Per-model verdicts:", "bold")
    for reviewer in data.get("reviewers", []):
        v = reviewer["verdict"]
        icon = "✅" if v == "PASS" else ("❌" if v == "FAIL" else "⏭️")
        color = "green" if v == "PASS" else ("red" if v == "FAIL" else "yellow")
        print_colored(f"    {icon} {reviewer['model']}: {v}", color)
        if reviewer.get("error"):
            print_colored(f"       Error: {reviewer['error']}", "dim")
    print()

    # Issues
    issues = data.get("issues", [])
    if issues:
        print_colored(f"  Issues ({len(issues)}):", "red")
        for issue in issues:
            print(f"    • {issue}")
        print()

    # Notes from each model
    has_notes = any(r.get("notes") for r in data.get("reviewers", []))
    if has_notes:
        print_colored("  Notes:", "blue")
        for reviewer in data.get("reviewers", []):
            for note in reviewer.get("notes", []):
                print(f"    [{reviewer['model']}] {note}")
        print()

    # Token usage
    tokens = data.get("tokens_used", {})
    if tokens:
        print_colored(
            f"  Tokens: {tokens.get('input', 0):,} in / {tokens.get('output', 0):,} out",
            "dim",
        )

    return 0 if data["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
