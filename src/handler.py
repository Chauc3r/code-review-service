"""
Multi-model code review Lambda service.

Accepts a git diff via HTTP POST, sends it to 5 LLMs in parallel,
and returns a majority-vote PASS/FAIL verdict.
"""

import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
import requests

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE", "review-api-keys")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
MAX_DIFF_CHARS = 50_000

SYSTEM_PROMPT = "You are a thorough senior code reviewer. Follow the response format exactly."

REVIEW_PROMPT_TEMPLATE = """You are a senior code reviewer evaluating a set of code changes.
Be thorough and verbose in your analysis.

## Context
Automatic code review gate.

## Code Changes
```diff
{diff}
```

## Evaluation Criteria
Evaluate each area. For each, explain what you checked and whether it passes:

1. **Correctness**: Logic bugs, off-by-one, race conditions, incorrect assumptions?
2. **Security** (OWASP-informed — check ALL that apply):
   - **Injection**: SQL injection, NoSQL injection, OS command injection, LDAP injection, template injection (SSTI)
   - **XSS**: Unescaped user input in HTML/templates, dangerouslySetInnerHTML, innerHTML, unsanitized URL params
   - **Secrets**: Hardcoded API keys, tokens, passwords, connection strings. Check for anything that looks like sk-, AKIA, ghp_, Bearer, base64-encoded credentials
   - **Auth/Access**: Missing authentication checks, broken access control, IDOR, privilege escalation
   - **SSRF**: User-controlled URLs passed to HTTP clients without allowlist validation
   - **Path traversal**: User input in file paths without sanitization
   - **Insecure defaults**: HTTP instead of HTTPS, verify=False, rejectUnauthorized: false, overly permissive CORS, missing CSP headers
   - **Deserialization**: Unsafe pickle.loads, yaml.load without SafeLoader, JSON.parse of untrusted data
   - **Cryptography**: Weak algorithms (MD5, SHA1 for security), hardcoded IVs/salts, Math.random() for security purposes
3. **Best practices**: Modern, idiomatic code? Current library versions? Deprecated APIs?
4. **Error handling**: Missing try/catch? Unhandled null/undefined? Edge cases? Sensitive info leaked in error messages?
5. **Architecture**: Well-structured? Separation of concerns? Code smells?
6. **Performance**: N+1 queries, unnecessary loops, memory leaks, blocking ops?

## Response Format
You MUST respond with exactly this structure:

VERDICT: PASS or FAIL

ANALYSIS:
[1-3 sentences per criterion. Reference file:line where relevant.]

ISSUES:
- [Each blocking issue. Include file:line. Explain WHY and WHAT to do instead.]

NOTES:
- [Non-blocking observations and positive feedback.]

Only FAIL for real problems — not style preferences."""

BEDROCK_MODELS = [
    {"name": "Qwen3 Coder Next", "model_id": "qwen.qwen3-coder-next"},
    {"name": "DeepSeek V3.2", "model_id": "deepseek.v3.2"},
    {"name": "Kimi K2.5", "model_id": "moonshotai.kimi-k2.5"},
    {"name": "Devstral 2 123B", "model_id": "mistral.devstral-2-123b"},
]

OPENROUTER_MODEL = {
    "name": "Gemini 3.1 Pro",
    "model_id": "google/gemini-3.1-pro-preview",
}

# ---------------------------------------------------------------------------
# Clients (initialized once per Lambda container)
# ---------------------------------------------------------------------------

bedrock_client = boto3.client("bedrock-runtime", region_name="eu-west-2")
dynamodb = boto3.resource("dynamodb", region_name="eu-west-2")


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def authenticate(api_key: str) -> dict | None:
    """Validate API key against DynamoDB. Returns developer info or None.

    Uses a conditional update to atomically check enabled=true AND increment
    usage_count in a single operation, avoiding read-then-write race conditions.
    """
    table = dynamodb.Table(DYNAMODB_TABLE)
    try:
        resp = table.update_item(
            Key={"api_key": api_key},
            UpdateExpression="ADD usage_count :inc",
            ConditionExpression="attribute_exists(api_key) AND enabled = :true",
            ExpressionAttributeValues={":inc": 1, ":true": True},
            ReturnValues="ALL_NEW",
        )
        item = resp.get("Attributes", {})
        return {"developer_name": item.get("developer_name", "unknown")}
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        return None


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def parse_verdict(text: str) -> str:
    """Extract PASS or FAIL from model response."""
    match = re.search(r"VERDICT:\s*(PASS|FAIL)", text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return "FAIL"


def parse_section(text: str, section_name: str) -> list[str]:
    """Extract bullet points from a named section."""
    pattern = rf"(?:^|\n){section_name}:\s*\n(.*?)(?=\n[A-Z]+:\s*\n|\Z)"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if not match:
        return []
    block = match.group(1)
    items = []
    for line in block.strip().split("\n"):
        line = line.strip()
        if line.startswith("- "):
            items.append(line[2:].strip())
    return items


# ---------------------------------------------------------------------------
# Model callers
# ---------------------------------------------------------------------------


def call_bedrock(model_config: dict, prompt: str, developer: str = "unknown") -> dict:
    """Call a Bedrock model via the Converse API."""
    try:
        response = bedrock_client.converse(
            modelId=model_config["model_id"],
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            system=[{"text": SYSTEM_PROMPT}],
            inferenceConfig={
                "temperature": 0.3,
                "maxTokens": 4096,
            },
            requestMetadata={
                "developer": developer,
                "service": "code-review",
            },
        )
        text = response["output"]["message"]["content"][0]["text"]
        usage = response.get("usage", {})
        return {
            "model": model_config["name"],
            "status": "ok",
            "text": text,
            "verdict": parse_verdict(text),
            "issues": parse_section(text, "ISSUES"),
            "notes": parse_section(text, "NOTES"),
            "tokens": {
                "input": usage.get("inputTokens", 0),
                "output": usage.get("outputTokens", 0),
            },
        }
    except Exception as e:
        logger.error("Bedrock error (%s): %s", model_config["name"], str(e))
        return {
            "model": model_config["name"],
            "status": "error",
            "error": f"Model call failed ({type(e).__name__})",
            "verdict": "SKIP",
            "issues": [],
            "notes": [],
            "tokens": {"input": 0, "output": 0},
        }


def call_openrouter(model_config: dict, prompt: str) -> dict:
    """Call an OpenRouter model via the chat completions API."""
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model_config["model_id"],
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 4096,
            },
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return {
            "model": model_config["name"],
            "status": "ok",
            "text": text,
            "verdict": parse_verdict(text),
            "issues": parse_section(text, "ISSUES"),
            "notes": parse_section(text, "NOTES"),
            "tokens": {
                "input": usage.get("prompt_tokens", 0),
                "output": usage.get("completion_tokens", 0),
            },
        }
    except Exception as e:
        logger.error("OpenRouter error (%s): %s", model_config["name"], str(e))
        return {
            "model": model_config["name"],
            "status": "error",
            "error": f"Model call failed ({type(e).__name__})",
            "verdict": "SKIP",
            "issues": [],
            "notes": [],
            "tokens": {"input": 0, "output": 0},
        }


# ---------------------------------------------------------------------------
# Core review logic
# ---------------------------------------------------------------------------


def run_review(diff: str, developer: str = "unknown") -> dict:
    """Send diff to all 5 models in parallel, aggregate results."""
    prompt = REVIEW_PROMPT_TEMPLATE.replace("{diff}", diff)
    results = []

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {}
        # Submit all Bedrock models (tagged with developer for cost allocation)
        for model in BEDROCK_MODELS:
            futures[executor.submit(call_bedrock, model, prompt, developer)] = model["name"]
        # Submit OpenRouter model
        futures[executor.submit(call_openrouter, OPENROUTER_MODEL, prompt)] = (
            OPENROUTER_MODEL["name"]
        )

        for future in as_completed(futures):
            results.append(future.result())

    # Tally votes (exclude SKIPs)
    pass_count = sum(1 for r in results if r["verdict"] == "PASS")
    fail_count = sum(1 for r in results if r["verdict"] == "FAIL")
    responded = pass_count + fail_count

    if responded < 3:
        final_verdict = "FAIL"
        warning = f"Only {responded}/5 models responded — defaulting to FAIL (quorum not reached)"
    else:
        final_verdict = "PASS" if pass_count > fail_count else "FAIL"
        warning = None

    # Deduplicate issues (full normalized text)
    seen = set()
    all_issues = []
    for r in results:
        for issue in r["issues"]:
            key = issue.lower().strip()
            if key not in seen:
                seen.add(key)
                all_issues.append(issue)

    # Total tokens
    total_input = sum(r["tokens"]["input"] for r in results)
    total_output = sum(r["tokens"]["output"] for r in results)

    # Build reviewer summaries
    reviewers = []
    for r in results:
        reviewer = {
            "model": r["model"],
            "verdict": r["verdict"],
            "issues": r["issues"],
            "notes": r["notes"],
        }
        if r["status"] == "error":
            reviewer["error"] = r.get("error", "Unknown error")
        reviewers.append(reviewer)

    response = {
        "verdict": final_verdict,
        "vote_breakdown": f"PASS:{pass_count} FAIL:{fail_count} (of {len(results)} models)",
        "reviewers": reviewers,
        "issues": all_issues,
        "tokens_used": {"input": total_input, "output": total_output},
    }
    if warning:
        response["warning"] = warning

    return response


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------


def lambda_handler(event, context):
    """Main Lambda entry point for Function URL."""
    start = time.time()

    # Extract API key from headers
    headers = event.get("headers", {})
    api_key = headers.get("x-api-key", "")

    if not api_key:
        return {
            "statusCode": 401,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Missing x-api-key header"}),
        }

    # Authenticate
    auth = authenticate(api_key)
    if not auth:
        return {
            "statusCode": 401,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Invalid or disabled API key"}),
        }

    developer = auth["developer_name"]

    # Extract diff from body
    body = event.get("body", "")
    if event.get("isBase64Encoded", False):
        import base64

        try:
            body = base64.b64decode(body).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "Invalid request body encoding"}),
            }

    if not body or not body.strip():
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "No diff provided"}),
        }

    # Truncate if too large
    diff = body.strip()
    if len(diff) > MAX_DIFF_CHARS:
        omitted = len(diff) - MAX_DIFF_CHARS
        diff = diff[:MAX_DIFF_CHARS] + f"\n\n... (truncated, {omitted} chars omitted)"

    # Run the review
    result = run_review(diff, developer)
    result["developer"] = developer

    # Log summary
    elapsed = round(time.time() - start, 1)
    logger.info(
        "Review complete: developer=%s verdict=%s breakdown=%s tokens=%s elapsed=%ss",
        developer,
        result["verdict"],
        result["vote_breakdown"],
        result["tokens_used"],
        elapsed,
    )

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(result),
    }
