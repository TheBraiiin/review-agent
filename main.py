"""Entry point for the Code Review Agent.

Usage:
    python main.py <PR_URL> [--post]

Examples:
    python main.py https://github.com/owner/repo/pull/123
    python main.py https://github.com/owner/repo/pull/123 --post
"""

import sys
import os
from dotenv import load_dotenv
from github_client import GitHubClient
from agent import run_review_agent


def main():
    load_dotenv()

    # Validate environment
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    github_token = os.getenv("GITHUB_TOKEN")

    if not anthropic_key:
        print("Error: ANTHROPIC_API_KEY not set. Add it to your .env file.")
        sys.exit(1)
    if not github_token:
        print("Error: GITHUB_TOKEN not set. Add it to your .env file.")
        sys.exit(1)

    # Parse arguments
    if len(sys.argv) < 2:
        print("Usage: python main.py <PR_URL> [--post]")
        print("  --post  Actually post the review to GitHub (default: dry run)")
        sys.exit(1)

    pr_url = sys.argv[1]
    post_review = "--post" in sys.argv

    # Parse the PR URL
    try:
        owner, repo, pr_number = GitHubClient.parse_pr_url(pr_url)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Initialize GitHub client and fetch head SHA
    github = GitHubClient(github_token)

    try:
        pr_info = github.get_pr_info(owner, repo, pr_number)
    except Exception as e:
        print(f"Error fetching PR: {e}")
        sys.exit(1)

    head_sha = pr_info["head_sha"]

    if not post_review:
        print("Running in DRY RUN mode (use --post to post review to GitHub)")

    # Run the agent
    result = run_review_agent(
        github=github,
        owner=owner,
        repo=repo,
        pr_number=pr_number,
        head_sha=head_sha,
        post_review=post_review,
    )

    print("\n" + "=" * 60)
    print("REVIEW COMPLETE")
    print("=" * 60)
    print(result)


if __name__ == "__main__":
    main()
