import os
import asyncio
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from github import Github, Auth
from prompt_engine import review_pr, format_comment
from database import init_db, log_review, get_stats
from dotenv import load_dotenv
import uvicorn

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

auth = Auth.Token(os.getenv("GITHUB_TOKEN"))
g = Github(auth=auth)

init_db()

async def process_pr(payload):
    try:
        pr_number = payload["pull_request"]["number"]
        repo_name = payload["repository"]["full_name"]
        pr_title = payload["pull_request"]["title"]
        pr_body = payload["pull_request"]["body"] or ""

        print(f"Processing PR #{pr_number}: {pr_title}")

        repo = g.get_repo(repo_name)
        pr = repo.get_pull(pr_number)

        diff_data = []
        for file in pr.get_files():
            try:
                full_content = repo.get_contents(file.filename, ref=pr.head.sha).decoded_content.decode()
            except Exception as e:
                print(f"Could not fetch {file.filename}: {e}")
                full_content = ""
            diff_data.append({
                "filename": file.filename,
                "patch": file.patch or "",
                "full_content": full_content
            })

        pr_context = {
            "title": pr_title,
            "description": pr_body,
            "commits": [c.commit.message for c in pr.get_commits()],
            "files": diff_data
        }

        all_reviews = await review_pr(pr_context)
        
        total_issues = sum(len(r.get("issues", [])) for r in all_reviews)
        log_review(repo_name, pr_number, pr_title, len(all_reviews), total_issues)

        comment = format_comment(all_reviews)
        pr.create_issue_comment(comment)
        print("Review posted successfully")

    except Exception as e:
        print(f"Error processing PR: {e}")

@app.post("/webhook")
async def handle_pr(request: Request, background_tasks: BackgroundTasks):
    payload = await request.json()
    if payload.get("action") not in ["opened", "synchronize"]:
        return {"status": "ignored"}
    background_tasks.add_task(process_pr, payload)
    return {"status": "received"}

@app.get("/stats")
async def stats():
    return get_stats()

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))