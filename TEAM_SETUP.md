# AI Code Review — Setup Guide

We now have a shared code review service that sends your changes to **5 different AI models** in parallel and gives you a majority-vote PASS/FAIL verdict. You can trigger it directly from GitHub Copilot Chat in VS Code.

---

## What You Need

1. Your **API key** (I'll DM this to you separately)
2. The **review endpoint**: `https://tkh74xjucagh4nmwvjayby7ph40xkivm.lambda-url.eu-west-2.on.aws/`
3. VS Code with GitHub Copilot Chat installed
4. Python 3 installed (any recent version)

---

## Step 1: Set Environment Variables

You need two environment variables available in your terminal. Add these to your shell profile so they persist.

**Mac / Linux** — add to `~/.bashrc`, `~/.zshrc`, or `~/.profile`:

```bash
export REVIEW_API_KEY="your-key-here"
export REVIEW_URL="https://tkh74xjucagh4nmwvjayby7ph40xkivm.lambda-url.eu-west-2.on.aws/"
```

Then run `source ~/.zshrc` (or whichever file you edited).

**Windows (PowerShell)** — run once as admin:

```powershell
[System.Environment]::SetEnvironmentVariable("REVIEW_API_KEY", "your-key-here", "User")
[System.Environment]::SetEnvironmentVariable("REVIEW_URL", "https://tkh74xjucagh4nmwvjayby7ph40xkivm.lambda-url.eu-west-2.on.aws/", "User")
```

Then restart VS Code.

**Verify it works** — open a terminal in VS Code and run:

```bash
echo $REVIEW_API_KEY    # Mac/Linux
echo %REVIEW_API_KEY%   # Windows CMD
$env:REVIEW_API_KEY     # Windows PowerShell
```

You should see your key printed.

---

## Step 2: Download the Review Script

Download `review.py` from the repo and put it at the root of whichever project you want to review:

```bash
# From your project root
curl -o review.py https://raw.githubusercontent.com/Chauc3r/code-review-service/main/client/review.py
```

Or just copy the file manually — it's a single Python file with no dependencies beyond the standard library.

> **Tip:** You can also put `review.py` somewhere on your PATH and use it across all projects.

---

## Step 3: Set Up the Copilot Chat Mode

This lets you trigger a review by switching to the **"Code Review"** chat mode in Copilot Chat.

1. In your project root, create the folder `.github/chatmodes/` if it doesn't exist:

```bash
mkdir -p .github/chatmodes
```

2. Download the chat mode file:

```bash
curl -o .github/chatmodes/review.md https://raw.githubusercontent.com/Chauc3r/code-review-service/main/client/chatmodes/review.md
```

3. **Restart VS Code** (or reload the window with `Ctrl+Shift+P` → "Reload Window").

---

## Step 4: Run a Review

1. Make some code changes in your project (edit a file, don't commit yet)
2. Open **Copilot Chat** in VS Code (sidebar or `Ctrl+Shift+I`)
3. At the top of the chat panel, click the chat mode dropdown and select **"Code Review"**
4. Type something like: `Review my changes`
5. Wait ~30-60 seconds while 5 models analyse your code in parallel
6. You'll get back:
   - **PASS** or **FAIL** verdict
   - Vote breakdown (e.g. "4 of 5 models passed")
   - Each model's individual verdict
   - Specific issues with file paths and line numbers
   - Suggestions for fixes
7. If it FAILs, Copilot can offer to fix each issue for you right there in the chat

---

## Alternative: Run from Terminal

If you prefer the command line, just run the script directly:

```bash
# From your project root (with review.py present)
python review.py
```

It'll grab your staged changes (`git diff --staged`), or unstaged changes if nothing is staged, send them for review, and print a colourful summary. Exit code is `0` for PASS, `1` for FAIL.

---

## How It Works

Your diff gets sent to 5 AI models simultaneously:

| Model | Provider |
|-------|----------|
| Qwen3 Coder Next | AWS Bedrock |
| DeepSeek V3.2 | AWS Bedrock |
| Kimi K2.5 | AWS Bedrock |
| Devstral 2 123B | AWS Bedrock |
| Gemini 3.1 Pro | OpenRouter |

Each model independently reviews for: correctness, security (OWASP top 10), best practices, error handling, architecture, and performance.

**Majority vote**: If 3+ models say FAIL, the verdict is FAIL. This filters out false positives from any single model being overly strict.

---

## FAQ

**Q: Does it see my whole codebase?**
No. It only sees the diff — the lines you changed, plus a few lines of context. Nothing else leaves your machine.

**Q: Is there a size limit?**
Diffs over 50,000 characters get truncated. For normal PRs this is never an issue.

**Q: Can I use it in CI/CD?**
Yes. The `review.py` script exits with code 1 on FAIL, so you can add it as a pipeline step. We'll set that up separately if there's interest.

**Q: It's slow / timed out**
The Lambda has a 5-minute timeout. Typical reviews take 30-60 seconds. If a model is slow, the others still return — we only need 3 of 5 to produce a verdict.

**Q: I got a 401 error**
Your API key is wrong or disabled. Check that `REVIEW_API_KEY` is set correctly in your terminal environment (not just in a `.env` file — it needs to be a real env var).

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `REVIEW_API_KEY not set` | See Step 1 — make sure the env var is set in the terminal VS Code uses |
| `REVIEW_URL not set` | Same as above |
| `401 Unauthorized` | Check your API key is correct, ask me to verify it's enabled |
| `400 No diff provided` | You have no uncommitted changes — make some edits first |
| Chat mode not appearing | Make sure `.github/chatmodes/review.md` exists and you've reloaded VS Code |
| `ModuleNotFoundError: requests` | Run `pip install requests`, or the script will fall back to urllib automatically |

---

Any issues, ping me and I'll sort it out.
