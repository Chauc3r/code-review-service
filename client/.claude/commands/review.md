Run the 5-model AI code review gate against the current changes.

1. Run `git diff --staged` to get staged changes. If nothing is staged, run `git diff` instead.
2. If there are no changes, tell me there's nothing to review and stop.
3. Run the review client: `python client/review.py` (make sure REVIEW_API_KEY and REVIEW_URL environment variables are set).
4. Parse the JSON output and present the results clearly:
   - Show the overall PASS/FAIL verdict prominently
   - Show the vote breakdown (e.g., PASS:4 FAIL:1)
   - List each model's individual verdict
   - Show all blocking issues with file paths and explanations
   - Show any non-blocking notes
5. If the verdict is FAIL:
   - List each issue
   - Offer to fix them one by one
   - After fixing, suggest re-running the review
6. If the verdict is PASS:
   - Confirm the code passed review
   - Suggest the developer can proceed to commit/push
