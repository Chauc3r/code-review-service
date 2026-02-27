# Code Review Service

A Lambda-based code review service that sends git diffs to 5 LLMs in parallel and returns a majority-vote PASS/FAIL verdict.

## Architecture

```
git diff → POST → Lambda Function URL → 5 models in parallel → majority vote → JSON response
```

**Models:**
- Qwen3 Coder Next (Bedrock)
- DeepSeek V3.2 (Bedrock)
- Kimi K2.5 (Bedrock)
- Devstral 2 123B (Bedrock)
- Gemini 3.1 Pro (OpenRouter)

## Deployment

### Prerequisites

- AWS SAM CLI installed
- AWS credentials configured (profile: `Tealbroth`)
- An OpenRouter API key

### Deploy

```bash
sam build
sam deploy --guided \
  --profile Tealbroth \
  --region eu-west-2 \
  --parameter-overrides OpenRouterApiKey=your-key-here
```

After first deploy, subsequent deploys:

```bash
sam build && sam deploy --profile Tealbroth --region eu-west-2
```

Note the **Function URL** from the output — this is your `REVIEW_URL`.

### Enable Bedrock Models

Before first use, enable access to these models in the AWS Bedrock console (eu-west-2):
- `qwen.qwen3-coder-next`
- `deepseek.v3.2`
- `moonshotai.kimi-k2.5`
- `mistral.devstral-2-123b`

## Admin: Managing API Keys

```bash
# Create a key for a developer
python admin.py create alice

# List all keys
python admin.py list

# Disable a key
python admin.py disable <api-key-uuid>

# Enable a key
python admin.py enable <api-key-uuid>

# Show usage counts
python admin.py usage
```

## Client Setup

### Environment Variables

Each developer needs two environment variables:

```bash
export REVIEW_API_KEY="your-uuid-key"
export REVIEW_URL="https://xxxxxxx.lambda-url.eu-west-2.on.aws/"
```

### Python Client

```bash
cd client/
python review.py
```

### Bash Client

```bash
cd client/
chmod +x review.sh
./review.sh
```

Both clients:
1. Get `git diff --staged` (falls back to `git diff`)
2. POST the diff to the Lambda
3. Print a colourful PASS/FAIL summary with per-model verdicts and issues
4. Exit 0 for PASS, 1 for FAIL

## Claude Code Integration

Copy the command file into your project:

```bash
cp client/.claude/commands/review.md your-repo/.claude/commands/review.md
```

Then use `/review` in Claude Code to trigger a review.

## GitHub Copilot Chat Mode

Copy the chat mode file into your repo:

```bash
cp client/chatmodes/review.md your-repo/.github/chatmodes/review.md
```

Then select the "Code Review" chat mode in Copilot Chat to run reviews.

## API Reference

### POST /

**Headers:**
- `x-api-key` (required) — Developer API key
- `Content-Type: text/plain`

**Body:** Raw git diff text

**Response (200):**

```json
{
  "verdict": "PASS",
  "vote_breakdown": "PASS:4 FAIL:1 (of 5 models)",
  "reviewers": [
    {
      "model": "Qwen3 Coder Next",
      "verdict": "PASS",
      "issues": [],
      "notes": ["Clean implementation."]
    }
  ],
  "issues": ["file.py:42 — Missing null check"],
  "developer": "alice",
  "tokens_used": {"input": 12500, "output": 8200}
}
```

**Error responses:**
- `401` — Missing, invalid, or disabled API key
- `400` — No diff provided
- `500` — Internal error

## Configuration

| Setting | Value |
|---------|-------|
| Runtime | Python 3.12 |
| Timeout | 300s |
| Memory | 512 MB |
| Region | eu-west-2 |
| Max diff size | 50,000 chars (truncated beyond) |
| Majority threshold | 3 of 5 models must agree |
| Fallback | < 3 responses → PASS with warning |
