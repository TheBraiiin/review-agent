"""The agentic loop — the core learning piece of this project.

This module implements the tool-use loop manually using the base Anthropic SDK.
The loop sends messages to Claude, checks if it wants to call a tool, executes
the tool, appends the result, and repeats until Claude produces a final response.
"""

import anthropic
from tools import TOOL_DEFINITIONS, dispatch_tool
from github_client import GitHubClient

SYSTEM_PROMPT = """\
You are a senior code reviewer AND security engineer analyzing a GitHub pull request.
You will produce a two-part review: a **Code Review** and a **Security Audit**.

## Workflow

1. Fetch the PR info and diff using the available tools.
2. For any changed file where you need more context, fetch its full contents.
3. Perform both analyses (code review + security audit) on the changes.
4. Call submit_review with your combined findings.

---

## Part 1: Code Review

Analyze the changes for:
- **Bugs & correctness**: Logic errors, off-by-one, null/undefined risks, race conditions
- **Performance**: Unnecessary allocations, N+1 queries, missing indexes
- **Readability & style**: Naming, dead code, overly complex logic
- **Suggestions**: Concrete improvements with code examples when helpful

Guidelines:
- Be constructive and specific. Reference file paths and line numbers.
- Distinguish between blocking issues (request changes) and minor suggestions.
- If the code looks good, say so — don't invent problems.
- Focus on what matters. Not every PR needs 20 comments.

---

## Part 2: Security Audit

Perform a thorough security-focused analysis. Only flag issues where you are >80% \
confident of actual exploitability. Minimize false positives — it is better to miss \
a theoretical issue than to flood the review with noise.

### Categories to Examine

**Input Validation & Injection:**
- SQL injection via unsanitized user input
- Command injection in system calls or subprocesses
- XXE injection in XML parsing
- Template injection in templating engines
- NoSQL injection in database queries
- Path traversal in file operations (only if it touches the local filesystem)
- XSS vulnerabilities (reflected, stored, DOM-based)

**Authentication & Authorization:**
- Authentication bypass logic
- Privilege escalation paths
- Session management flaws
- JWT token vulnerabilities
- Authorization logic bypasses

**Crypto & Secrets Management:**
- Hardcoded API keys, passwords, or tokens in source code
- Weak cryptographic algorithms or implementations
- Improper key storage or management
- Certificate validation bypasses

**Code Execution & Deserialization:**
- Remote code execution via deserialization (pickle, YAML, etc.)
- eval/exec injection in dynamic code execution
- Unsafe use of dangerouslySetInnerHTML / bypassSecurityTrustHtml

**Data Exposure:**
- Sensitive data (PII, secrets, passwords) being logged
- API endpoint data leakage
- Debug information exposure in production

### Security Severity Levels
- **CRITICAL**: Directly exploitable RCE, authentication bypass, or data breach
- **HIGH**: Exploitable vulnerability with significant impact
- **MEDIUM**: Requires specific conditions but has real impact
- **LOW**: Defense-in-depth issue (only mention if very concrete)

### What NOT to Flag (Hard Exclusions)
- Denial of Service / resource exhaustion / rate limiting
- Secrets stored in .env files or environment variables (these are expected)
- Race conditions that are theoretical rather than practical
- SSRF where attacker only controls the path (not host/protocol)
- Log spoofing (outputting unsanitized input to logs)
- User-controlled content included in AI prompts
- Regex injection or regex DOS
- Lack of audit logs or general hardening measures
- Outdated third-party library versions
- Client-side JS/TS missing auth checks (that's the server's job)
- Memory safety issues in memory-safe languages (Rust, Go, Python, etc.)
- Issues only in test files

---

## Output Format

Structure your review as markdown with two clearly separated sections:

### Code Review Section
- Summary of what the PR does
- Line-level comments on bugs, performance, style
- Overall assessment

### Security Audit Section
For each finding, include:
- **File and line number**
- **Severity** (CRITICAL / HIGH / MEDIUM)
- **Category** (e.g., sql_injection, command_injection, xss, path_traversal)
- **Description** of the vulnerability
- **Exploit scenario** — how an attacker would exploit it
- **Recommendation** — specific fix with code example if possible

If no security issues are found, explicitly state: "No security vulnerabilities identified."

When calling submit_review, use REQUEST_CHANGES if there are any HIGH or CRITICAL \
security findings. Use COMMENT for everything else.
"""

MODEL = "claude-sonnet-4-20250514"


def run_review_agent(
    github: GitHubClient,
    owner: str,
    repo: str,
    pr_number: int,
    head_sha: str,
    post_review: bool = False,
) -> str:
    """Run the agentic loop to review a PR.

    Returns the final text response from Claude (the review summary).
    """
    client = anthropic.Anthropic()

    # Start the conversation with a user message asking for a review
    messages = [
        {
            "role": "user",
            "content": (
                f"Please review GitHub PR #{pr_number} in {owner}/{repo}. "
                "Start by fetching the PR info and diff, analyze the changes, "
                "and submit your review."
            ),
        }
    ]

    print(f"\n{'='*60}")
    print(f"Starting review of {owner}/{repo}#{pr_number}")
    print(f"{'='*60}\n")

    # --- The Agentic Loop ---
    while True:
        # Step 1: Send messages + tool definitions to Claude
        response = client.messages.create(
            model=MODEL,
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        # Step 2: Check the stop reason
        if response.stop_reason == "end_turn":
            # Claude is done — extract and return the final text
            final_text = ""
            for block in response.content:
                if block.type == "text":
                    final_text += block.text
            return final_text

        elif response.stop_reason == "tool_use":
            # Claude wants to call one or more tools

            # Append Claude's response (with tool_use blocks) to history
            messages.append({"role": "assistant", "content": response.content})

            # Process each tool call in the response
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input
                    tool_use_id = block.id

                    print(f"  Tool call: {tool_name}({tool_input})")

                    # Step 3: Execute the tool
                    try:
                        result = dispatch_tool(
                            tool_name=tool_name,
                            tool_input=tool_input,
                            github=github,
                            owner=owner,
                            repo=repo,
                            pr_number=pr_number,
                            head_sha=head_sha,
                            post_review=post_review,
                        )
                    except Exception as e:
                        result = f"Error executing tool: {e}"

                    # Collect tool results
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": result,
                        }
                    )

                    # Print a preview of the result
                    preview = result[:200] + "..." if len(result) > 200 else result
                    print(f"  Result: {preview}\n")

            # Step 4: Append tool results and loop back
            messages.append({"role": "user", "content": tool_results})

        else:
            # Unexpected stop reason
            print(f"Unexpected stop reason: {response.stop_reason}")
            return f"Agent stopped unexpectedly: {response.stop_reason}"
