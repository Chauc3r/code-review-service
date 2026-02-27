#!/usr/bin/env bash
# Code review client — sends git diff to the review Lambda and prints results.
#
# Environment variables:
#   REVIEW_API_KEY  — Your personal API key
#   REVIEW_URL      — Lambda Function URL endpoint

set -euo pipefail

RED='\033[91m'
GREEN='\033[92m'
YELLOW='\033[93m'
BLUE='\033[94m'
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

if [[ -z "${REVIEW_API_KEY:-}" ]]; then
    echo -e "${RED}Error: REVIEW_API_KEY environment variable not set.${RESET}"
    exit 1
fi

if [[ -z "${REVIEW_URL:-}" ]]; then
    echo -e "${RED}Error: REVIEW_URL environment variable not set.${RESET}"
    exit 1
fi

# Get diff — prefer staged, fall back to unstaged
DIFF=$(git diff --staged)
if [[ -z "$DIFF" ]]; then
    DIFF=$(git diff)
fi

if [[ -z "$DIFF" ]]; then
    echo -e "${YELLOW}No changes to review (no staged or unstaged diff).${RESET}"
    exit 0
fi

DIFF_SIZE=${#DIFF}
echo -e "${BLUE}Sending diff for review...${RESET}"
echo "  Diff size: ${DIFF_SIZE} characters"
echo

# POST diff to the review service
RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "$REVIEW_URL" \
    -H "Content-Type: text/plain" \
    -H "x-api-key: $REVIEW_API_KEY" \
    --data-binary "$DIFF" \
    --max-time 300)

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [[ "$HTTP_CODE" != "200" ]]; then
    echo -e "${RED}HTTP ${HTTP_CODE}: ${BODY}${RESET}"
    exit 1
fi

# Parse verdict
VERDICT=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['verdict'])")
BREAKDOWN=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['vote_breakdown'])")

echo
if [[ "$VERDICT" == "PASS" ]]; then
    echo -e "${GREEN}  ╔═══════════════╗${RESET}"
    echo -e "${GREEN}  ║   PASS  ✅    ║${RESET}"
    echo -e "${GREEN}  ╚═══════════════╝${RESET}"
else
    echo -e "${RED}  ╔═══════════════╗${RESET}"
    echo -e "${RED}  ║   FAIL  ❌    ║${RESET}"
    echo -e "${RED}  ╚═══════════════╝${RESET}"
fi

echo
echo -e "${BOLD}  Vote: ${BREAKDOWN}${RESET}"
echo

# Per-model verdicts
echo -e "${BOLD}  Per-model verdicts:${RESET}"
echo "$BODY" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for r in data.get('reviewers', []):
    v = r['verdict']
    icon = '✅' if v == 'PASS' else ('❌' if v == 'FAIL' else '⏭️')
    print(f'    {icon} {r[\"model\"]}: {v}')
    if r.get('error'):
        print(f'       Error: {r[\"error\"]}')
"
echo

# Issues
echo "$BODY" | python3 -c "
import sys, json
data = json.load(sys.stdin)
issues = data.get('issues', [])
if issues:
    print(f'  Issues ({len(issues)}):')
    for i in issues:
        print(f'    • {i}')
    print()
"

# Notes
echo "$BODY" | python3 -c "
import sys, json
data = json.load(sys.stdin)
has_notes = any(r.get('notes') for r in data.get('reviewers', []))
if has_notes:
    print('  Notes:')
    for r in data.get('reviewers', []):
        for n in r.get('notes', []):
            print(f'    [{r[\"model\"]}] {n}')
    print()
"

# Token usage
echo "$BODY" | python3 -c "
import sys, json
data = json.load(sys.stdin)
t = data.get('tokens_used', {})
if t:
    print(f'  Tokens: {t.get(\"input\", 0):,} in / {t.get(\"output\", 0):,} out')
"

if [[ "$VERDICT" == "PASS" ]]; then
    exit 0
else
    exit 1
fi
