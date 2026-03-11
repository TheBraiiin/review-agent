# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Agent

```bash
source .venv/bin/activate
python main.py <PR_URL>            # dry run (no GitHub posting)
python main.py <PR_URL> --post     # posts review to GitHub
```

Requires `.env` with `ANTHROPIC_API_KEY` and `GITHUB_TOKEN` (see `.env.example`).

## Installing Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Architecture

This is a learning project that implements a Claude tool-use agentic loop manually (no Agent SDK). Given a GitHub PR URL, it fetches the diff, analyzes code with Claude, and produces a structured review.

**Data flow:** `main.py` parses the PR URL and validates env vars → `agent.py` runs the agentic while-loop (send messages to Claude, execute tool calls, append results, repeat until `stop_reason == "end_turn"`) → `tools.py` defines tool JSON schemas and dispatches calls → `github_client.py` makes GitHub REST API requests.

**Key design decisions:**
- Tool schemas in `TOOL_DEFINITIONS` (tools.py) take no repo/PR params — those are closed over by `dispatch_tool`, since the agent operates on a single PR per run.
- The agent uses `stop_reason` to decide flow: `"tool_use"` means execute tools and loop, `"end_turn"` means return the final review text.
- `--post` flag controls whether `submit_review` actually calls the GitHub API or returns a dry-run preview. This is handled in `dispatch_tool`, not in the tool schema.
- Large diffs are truncated at 100k chars in `dispatch_tool` to stay within context limits.
- The system prompt in `agent.py` shapes Claude into a senior code reviewer and instructs it to call `submit_review` when done.
- Model is set via `MODEL` constant in `agent.py` (currently `claude-sonnet-4-20250514`).
