# Code Review SOP

## When assigned a review ticket, follow these steps exactly:

1. Read all files in the task's workspace directory
2. Check for:
   - Syntax errors and typos
   - Missing error handling
   - Hardcoded secrets or credentials
   - Logic bugs and edge cases
   - Missing input validation
3. Write a `review.md` file with findings grouped by severity:
   - **CRITICAL**: Must fix before merge (bugs, security issues)
   - **WARN**: Should fix (poor patterns, missing edge cases)
   - **INFO**: Nice to fix (style, naming, documentation)
4. Update the ticket status to "review"
5. If CRITICAL issues found: reassign to original developer with review.md
6. If no CRITICAL issues: update ticket status to "done"
