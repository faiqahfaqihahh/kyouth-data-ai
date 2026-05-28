import os
import sys
import sqlite3
import tempfile
from pathlib import Path

WEEK2_DIR = Path(__file__).parent / "week_2"
sys.path.insert(0, str(WEEK2_DIR))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from find_skil_gaps import _find_skill_gaps_async, SkillGapResult, DailyQuotaExceededError

load_dotenv()

# ── App setup ───────────────────────────────────────────────────────────
app = FastAPI()

# Crucial for microservice cross-origin architecture! 
# This permits our Frontend running on port 8000 to talk to our Backend on port 8001.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this to explicit domains in strict production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_URL = os.getenv("DB_URL", "week_2/resources/jobs_d1.db")


# ── Health check ────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}


# ── Chat endpoint ────────────────────────────────────────────────────────
@app.post("/chat")
async def chat(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON body"})

    message: str = body.get("message", "").strip()
    pdf_text: str | None = body.get("pdf_text", None)

    if not message and not pdf_text:
        return JSONResponse(status_code=400, content={"error": "No message or PDF provided"})

    resume_text = pdf_text if pdf_text else message

    # ← ADD THIS: log what we received
    print(f"Received message: '{message[:100]}'")
    print(f"PDF text present: {pdf_text is not None}")
    print(f"Resume text length: {len(resume_text)}")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(resume_text)
            tmp_path = tmp.name

        print(f"Temp file created: {tmp_path}")
        result = await _find_skill_gaps_async(tmp_path, DB_URL)
        print(f"Result gaps: {result.gaps}")
        print(f"Result skill_demand: {result.skill_demand}")
        
    except DailyQuotaExceededError as e:
        return JSONResponse(
            status_code=429,
            content={"error": str(e)}
        )
    except Exception as e:
        # ← ADD THIS: print the full traceback
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": f"Processing failed: {str(e)}"})
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    # ← ADD THIS: guard against empty result
    if result is None:
        return JSONResponse(status_code=500, content={"error": "No result returned"})

    if not result.gaps:
        reply = "Great news! No skill gaps found."
    else:
        top_skills = sorted(result.skill_demand.items(), key=lambda x: -x[1])[:5]
        top_str = ", ".join(f"{s} ({c} job{'s' if c > 1 else ''})" for s, c in top_skills)
        reply = (
            f"I found {len(result.gaps)} skill gap(s).\n\n"
            f"Missing skills: {', '.join(result.gaps)}\n\n"
            f"Most in-demand: {top_str}"
        )

    return JSONResponse(content={"reply": reply})


# ── Database visualisation endpoints (Bonus) ─────────────────────────

def get_db():
    return sqlite3.connect(DB_URL)

@app.get("/api/stats/tech-distribution")
def tech_distribution():
    """Returns skill -> job count for pie chart."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT tech_stack FROM jobs WHERE tech_stack IS NOT NULL AND tech_stack != ''"
        )
        rows = cursor.fetchall()
        conn.close()

        demand: dict = {}
        for (stack,) in rows:
            for skill in stack.split(","):
                skill = skill.strip().lower()
                if skill and skill not in {"not specified", "n/a", "none"}:
                    demand[skill] = demand.get(skill, 0) + 1

        # Return top 10 for readability
        top = sorted(demand.items(), key=lambda x: -x[1])[:10]
        return JSONResponse(content={
            "labels": [k for k, v in top],
            "values": [v for k, v in top],
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/stats/jobs-per-source")
def jobs_per_source():
    """Returns job count — used for bar chart."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        # Count tagged vs untagged
        cursor.execute("""
            SELECT
                CASE
                    WHEN tech_stack IS NULL OR tech_stack = '' THEN 'Untagged'
                    ELSE 'Tagged'
                END as status,
                COUNT(*) as count
            FROM jobs
            GROUP BY status
        """)
        rows = cursor.fetchall()
        conn.close()
        return JSONResponse(content={
            "labels": [r[0] for r in rows],
            "values": [r[1] for r in rows],
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/jobs/search")
def search_jobs(q: str = ""):
    """Search jobs by keyword in description or tech_stack."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        like = f"%{q}%"
        cursor.execute("""
            SELECT source_id, tech_stack, description
            FROM jobs
            WHERE tech_stack LIKE ? OR description LIKE ?
            LIMIT 20
        """, (like, like))
        rows = cursor.fetchall()
        conn.close()
        return JSONResponse(content={
            "results": [
                {
                    "source_id": r[0],
                    "tech_stack": r[1],
                    "description": r[2][:200] + "..." if r[2] and len(r[2]) > 200 else r[2],
                }
                for r in rows
            ]
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})