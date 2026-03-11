"""The agentic loop — the core learning piece of this project.

This module implements the tool-use loop manually using the base Anthropic SDK.
The loop sends messages to Claude, checks if it wants to call a tool, executes
the tool, appends the result, and repeats until Claude produces a final response.
"""

import anthropic
from tools import TOOL_DEFINITIONS, dispatch_tool
from github_client import GitHubClient

SYSTEM_PROMPT = """\
You are a senior code reviewer analyzing a GitHub pull request. Your job is to:

1. First, fetch the PR info and diff using the available tools.
2. Analyze the changes carefully. If you need more context about a specific file, \
fetch its full contents.
3. Produce a thorough but concise review covering:
   - **Bugs & correctness**: Logic errors, off-by-one, null/undefined risks, race conditions
   - **Security**: Injection, auth issues, secrets in code, unsafe deserialization
   - **Performance**: Unnecessary allocations, N+1 queries, missing indexes
   - **Readability & style**: Naming, dead code, overly complex logic
   - **Suggestions**: Concrete improvements with code examples when helpful
4. When you're done, call submit_review with your findings.

Guidelines:
- Be constructive and specific. Reference file paths and line numbers.
- Distinguish between blocking issues (request changes) and minor suggestions (comment).
- If the PR looks good, say so — don't invent problems.
- Focus on what matters. Not every PR needs 20 comments.
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
            max_tokens=4096,
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
