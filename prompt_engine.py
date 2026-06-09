'''
   Updated Version : 1.1
   Uses Groq Backend, fully deployable 
'''

import json
import asyncio
from groq import Groq
import os
from dotenv import load_dotenv
load_dotenv()

SKIP_EXTENSIONS = {
    '.lock', '.json', '.png', '.jpg', '.jpeg', '.gif', '.svg',
    '.ico', '.pdf', '.zip', '.tar', '.gz', '.env', '.csv'
}

SYSTEM_PROMPT = """You are a senior software engineer conducting a thorough code review.
Analyze the provided code changes and return your review in this exact JSON format:

{
    "issues": [
        {
            "severity": "critical|warning|suggestion",
            "line": <line number or null>,
            "issue": "clear description of the problem",
            "suggestion": "exactly how to fix it"
        }
    ],
    "summary": "one line overall assessment",
    "suggestion": "exactly how to fix it, include before/after code snippet"
}

Return only valid JSON, no extra text."""

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def should_skip(filename):
    return any(filename.endswith(ext) for ext in SKIP_EXTENSIONS)


def extract_relevant_context(full_content, patch):
    if not patch:
        return full_content[:3000]
    
    changed_lines = set()
    current_line = 0
    for line in patch.split('\n'):
        if line.startswith('@@'):
            try:
                start = int(line.split('+')[1].split(',')[0])
                current_line = start
            except:
                pass
        elif not line.startswith('-'):
            changed_lines.add(current_line)
            current_line += 1

    lines = full_content.split('\n')
    relevant = set()
    for l in changed_lines:
        for i in range(max(0, l - 10), min(len(lines), l + 10)):
            relevant.add(i)

    context = '\n'.join(lines[i] for i in sorted(relevant))
    return context[:3000]


def build_user_prompt(pr_context, file):
    relevant_context = extract_relevant_context(
        file['full_content'],
        file['patch']
    )
    return f"""
PR Title: {pr_context['title']}
PR Description: {pr_context['description']}
Commit Messages: {', '.join(pr_context['commits'])}

File: {file['filename']}

Changes (diff):
{file['patch']}

Relevant context:
{relevant_context}

Review this file based on the PR context above.
"""


async def review_file_async(pr_context, file):
    if should_skip(file['filename']):
        print(f"Skipping {file['filename']}")
        return None

    print(f"Reviewing file: {file['filename']}")

    loop = asyncio.get_event_loop()

    def run_groq():
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(pr_context, file)}
            ],
            temperature=0.1,
            max_tokens=4096
        )
        return response.choices[0].message.content
    
    try:
        raw = await loop.run_in_executor(None, run_groq)
        print(f"Raw response for {file['filename']}:\n{raw}")

        # strip thinking block if present
        if "<think>" in raw:
            raw = raw.split("</think>")[-1].strip()

        clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

        try:
            result = json.loads(clean)
            result['filename'] = file['filename']
            return result
        except json.JSONDecodeError as e:
            print(f"JSON parse failed for {file['filename']}: {e}")
            return {"filename": file['filename'], "issues": [], "summary": "Failed to parse review"}

    except Exception as e:
        print(f"Groq call failed for {file['filename']}: {e}")
        return {"filename": file['filename'], "issues": [], "summary": "Groq call failed"}


async def review_pr(pr_context):
    print(f"Starting review for PR: {pr_context['title']}")
    print(f"Files to review: {[f['filename'] for f in pr_context['files']]}")

    tasks = [review_file_async(pr_context, file) for file in pr_context['files']]
    results = await asyncio.gather(*tasks)

    all_reviews = [r for r in results if r is not None]
    print(f"Review complete, {len(all_reviews)} files reviewed")
    return all_reviews


def format_comment(all_reviews):
    print("Formatting comment...")
    comment = "## PRism Review 🔍\n\n"

    for review in all_reviews:
        comment += f"### `{review['filename']}`\n"
        comment += f"{review['summary']}\n\n"

        for issue in review['issues']:
            emoji = {"critical": "🔴", "warning": "🟡", "suggestion": "🟢"}.get(issue['severity'], "⚪")
            line = f"Line {issue['line']}" if issue['line'] else "General"
            comment += f"{emoji} **{issue['severity'].upper()}** — {line}\n"
            comment += f"**Issue:** {issue['issue']}\n"
            comment += f"**Fix:** {issue['suggestion']}\n\n"

    print("Comment formatted successfully")
    return comment