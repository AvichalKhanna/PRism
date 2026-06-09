# PRism 🔍

PRism is a self-hosted AI code review agent that automatically reviews GitHub Pull Requests using a large language model. It hooks into your repository via GitHub webhooks, analyzes code diffs with full file context, and posts structured feedback directly as PR comments — flagging bugs, security issues, and code quality problems with exact line numbers and fix suggestions.

## How it works
When a PR is opened or updated, PRism receives the webhook, pulls the diff and surrounding code context via the GitHub API, and sends it to Qwen3-32B running on Groq for analysis. Each file is reviewed in parallel for speed. Reviews are structured by severity (critical, warning, suggestion) and posted back to the PR within seconds. All review activity is logged to a Supabase PostgreSQL database and exposed via a `/stats` API endpoint.

## Stack
FastAPI · PyGitHub · Groq (Qwen3-32B) · Supabase PostgreSQL · Railway
