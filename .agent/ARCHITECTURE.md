# Code Review Service — Architecture

## Overview
Lambda-based multi-model code review service. Accepts git diffs via HTTP POST, sends to 5 LLMs in parallel, returns majority-vote PASS/FAIL verdict.

## System Invariants
- **AWS Profile**: `Tealbroth`
- **Region**: `eu-west-2`
- **Runtime**: Python 3.12
- **Project tag**: `code-review-service`

## Architecture
```
POST (diff + x-api-key) → Lambda Function URL (AUTH_TYPE: NONE)
  → DynamoDB auth check (review-api-keys table)
  → 5 parallel model calls (4 Bedrock + 1 OpenRouter)
  → Majority vote aggregation
  → JSON response
```

## Key Files
| File | Purpose |
|------|---------|
| `template.yaml` | SAM deployment template (Lambda + DynamoDB + IAM) |
| `src/handler.py` | Lambda handler — auth, model calls, voting, response |
| `admin.py` | CLI for managing API keys in DynamoDB |
| `client/review.py` | Python client script for devs |
| `client/review.sh` | Bash client script for devs |
| `client/.claude/commands/review.md` | Claude Code `/review` command |
| `client/chatmodes/review.md` | Copilot Chat mode (copy to `.github/chatmodes/`) |

## Models
| Model | Provider | Model ID |
|-------|----------|----------|
| Qwen3 Coder Next | Bedrock | `qwen.qwen3-coder-next` |
| DeepSeek V3.2 | Bedrock | `deepseek.v3.2` |
| Kimi K2.5 | Bedrock | `moonshotai.kimi-k2.5` |
| Devstral 2 123B | Bedrock | `mistral.devstral-2-123b` |
| Gemini 3.1 Pro | OpenRouter | `google/gemini-3.1-pro-preview` |

## Auth Flow
1. `x-api-key` header → DynamoDB lookup
2. Reject if missing/not found/disabled
3. Atomic `ADD usage_count :inc` update
4. Proceed with review

## Recent Changes Log
- 2026-02-27: Initial build — all files created
