# Code Review Service — Progress

## 2026-02-27: Initial Build
- [x] SAM template (template.yaml) — Lambda + DynamoDB + IAM + Function URL
- [x] Lambda handler (src/handler.py) — auth, 5 parallel model calls, voting, response parsing
- [x] Admin CLI (admin.py) — create/list/enable/disable/usage
- [x] Python client (client/review.py) — colourful terminal output
- [x] Bash client (client/review.sh) — colourful terminal output
- [x] Claude Code command (client/.claude/commands/review.md)
- [x] Copilot chat mode (client/chatmodes/review.md)
- [x] README with full docs

## Next Steps
- Deploy with `sam build && sam deploy --guided`
- Enable Bedrock model access in eu-west-2 console
- Create first API key: `python admin.py create <name>`
- Test end-to-end with a real diff
