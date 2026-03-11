"""GitHub API wrapper for fetching PR data and posting reviews."""

import re
import requests


class GitHubClient:
    """Handles all GitHub REST API interactions."""

    BASE_URL = "https://api.github.com"

    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
            }
        )

    @staticmethod
    def parse_pr_url(pr_url: str) -> tuple[str, str, int]:
        """Extract owner, repo, and PR number from a GitHub PR URL.

        Supports formats like:
            https://github.com/owner/repo/pull/123
        """
        match = re.match(
            r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)", pr_url
        )
        if not match:
            raise ValueError(f"Invalid GitHub PR URL: {pr_url}")
        return match.group(1), match.group(2), int(match.group(3))

    def get_pr_info(self, owner: str, repo: str, pr_number: int) -> dict:
        """Fetch PR metadata: title, description, author, branches."""
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/pulls/{pr_number}"
        resp = self.session.get(url)
        resp.raise_for_status()
        data = resp.json()
        return {
            "title": data["title"],
            "description": data.get("body") or "",
            "author": data["user"]["login"],
            "base_branch": data["base"]["ref"],
            "head_branch": data["head"]["ref"],
            "head_sha": data["head"]["sha"],
            "state": data["state"],
            "additions": data["additions"],
            "deletions": data["deletions"],
            "changed_files": data["changed_files"],
        }

    def get_pr_diff(self, owner: str, repo: str, pr_number: int) -> str:
        """Fetch the full diff of the PR."""
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/pulls/{pr_number}"
        resp = self.session.get(
            url, headers={"Accept": "application/vnd.github.v3.diff"}
        )
        resp.raise_for_status()
        return resp.text

    def get_file_contents(
        self, owner: str, repo: str, path: str, ref: str
    ) -> str:
        """Fetch a file's contents at a specific commit ref."""
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/contents/{path}"
        resp = self.session.get(
            url,
            params={"ref": ref},
            headers={"Accept": "application/vnd.github.v3.raw"},
        )
        resp.raise_for_status()
        return resp.text

    def submit_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        body: str,
        comments: list[dict] | None = None,
        event: str = "COMMENT",
    ) -> dict:
        """Post a review to the PR.

        Args:
            body: Top-level review summary.
            comments: List of line-level comments, each with keys:
                - path: file path
                - line: line number in the diff
                - body: comment text
            event: One of APPROVE, REQUEST_CHANGES, COMMENT.
        """
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
        payload = {"body": body, "event": event}
        if comments:
            payload["comments"] = [
                {
                    "path": c["path"],
                    "line": c["line"],
                    "body": c["body"],
                }
                for c in comments
            ]
        resp = self.session.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()
