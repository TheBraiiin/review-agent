"""Tool definitions (JSON schemas) and dispatcher for the code review agent."""

from github_client import GitHubClient

# --- Tool JSON schemas (sent to Claude) ---

TOOL_DEFINITIONS = [
    {
        "name": "get_pr_info",
        "description": (
            "Fetch PR metadata including title, description, author, "
            "base/head branches, and stats (additions, deletions, changed files)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_pr_diff",
        "description": (
            "Fetch the full unified diff of all changed files in the PR. "
            "Use this to see exactly what code was added, removed, or modified."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_file_contents",
        "description": (
            "Fetch the full contents of a specific file at the PR's head commit. "
            "Use this when you need more context about a file beyond what the diff shows."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path relative to the repo root.",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "submit_review",
        "description": (
            "Submit the final code review to GitHub. Call this once you have "
            "completed your analysis and are ready to post."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Top-level review summary in markdown.",
                },
                "comments": {
                    "type": "array",
                    "description": "Line-level review comments.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "File path relative to repo root.",
                            },
                            "line": {
                                "type": "integer",
                                "description": "Line number in the diff to comment on.",
                            },
                            "body": {
                                "type": "string",
                                "description": "The review comment in markdown.",
                            },
                        },
                        "required": ["path", "line", "body"],
                    },
                },
                "event": {
                    "type": "string",
                    "enum": ["APPROVE", "REQUEST_CHANGES", "COMMENT"],
                    "description": "Review verdict. Defaults to COMMENT.",
                },
            },
            "required": ["summary"],
        },
    },
]


def dispatch_tool(
    tool_name: str,
    tool_input: dict,
    github: GitHubClient,
    owner: str,
    repo: str,
    pr_number: int,
    head_sha: str,
    post_review: bool,
) -> str:
    """Execute a tool call and return the result as a string.

    This is the dispatcher — it maps tool names to actual function calls.
    """
    if tool_name == "get_pr_info":
        result = github.get_pr_info(owner, repo, pr_number)
        return _format_dict(result)

    elif tool_name == "get_pr_diff":
        diff = github.get_pr_diff(owner, repo, pr_number)
        # Truncate very large diffs to stay within context limits
        if len(diff) > 100_000:
            return diff[:100_000] + "\n\n... [diff truncated at 100k chars]"
        return diff

    elif tool_name == "get_file_contents":
        path = tool_input["path"]
        contents = github.get_file_contents(owner, repo, path, ref=head_sha)
        return contents

    elif tool_name == "submit_review":
        summary = tool_input["summary"]
        comments = tool_input.get("comments", [])
        event = tool_input.get("event", "COMMENT")

        if post_review:
            result = github.submit_review(
                owner, repo, pr_number, summary, comments, event
            )
            return f"Review posted successfully. Review ID: {result['id']}"
        else:
            # Dry-run mode: just return the review content
            review_preview = f"## Review ({event})\n\n{summary}\n"
            if comments:
                review_preview += f"\n### Line Comments ({len(comments)}):\n"
                for c in comments:
                    review_preview += (
                        f"\n**{c['path']}:{c['line']}**\n{c['body']}\n"
                    )
            return f"[DRY RUN — review not posted]\n\n{review_preview}"

    else:
        return f"Error: Unknown tool '{tool_name}'"


def _format_dict(d: dict) -> str:
    """Format a dict as a readable string for the model."""
    lines = []
    for key, value in d.items():
        lines.append(f"{key}: {value}")
    return "\n".join(lines)
