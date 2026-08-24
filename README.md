# Sift — Smart Resume Screener

A small, fully working tool that takes a job description and a batch of resumes
(PDF / DOCX / TXT), and returns a ranked shortlist of candidates with an
LLM-generated match score (1–10) and a written justification for each.

Built with **Flask + SQLite** on the backend and the **Gemini API** for
semantic extraction and scoring. Frontend is plain HTML/CSS/JS — no build step.

---

## How it works (architecture)

```
┌────────────┐      multipart upload      ┌───────────────┐
│  Browser   │ ───────────────────────────▶│  Flask API     │
│ (frontend/)│◀─────────────────────────── │  (backend/)    │
└────────────┘        JSON responses       └───────┬────────┘
                                                     │
                          ┌──────────────────────────┼──────────────────────────┐
                          ▼                          ▼                          ▼
                 resume_parser.py           gemini_service.py             database.py
                 (pdfplumber /               (one Gemini call per          (SQLite —
                  python-docx → text)         resume: extract +            jobs +
                                               score + justify, as         candidates)
                                               structured JSON)
```

**Flow for one resume:**
1. File is uploaded to `/api/jobs/<job_id>/resumes`.
2. `resume_parser.py` converts the file into plain text.
3. `gemini_service.py` sends the resume text + job description to Gemini in a
   single prompt and asks for **structured JSON back** (`response_mime_type:
   application/json`), containing extracted skills/experience/education *and*
   a 1–10 match score with justification — one API call does both jobs the
   brief asks for.
4. The parsed result is stored in SQLite (`resume_screener.db`) and returned
   to the browser.
5. The dashboard re-fetches `/api/jobs/<job_id>/candidates`, which the backend
   returns pre-sorted by score (best match first).

### Why this shape
- **One LLM call per resume**, not two — the same prompt extracts structured
  fields *and* scores the fit, which is faster and cheaper than separate
  extraction/scoring calls, while still satisfying both requirements in the
  brief.
- **SQLite** because it's zero-setup and this is a single-user/local tool —
  swapping in Postgres later is a one-file change (`database.py`).
- **No frontend framework** — the UI is small enough that React/Vue would
  just be overhead; plain JS keeps the whole stack readable in one sitting.

---

## Project layout

```
smart-resume-screener/
├── backend/
│   ├── app.py              # Flask routes
│   ├── database.py         # SQLite schema + queries
│   ├── resume_parser.py    # PDF/DOCX/TXT → plain text
│   ├── gemini_service.py   # Gemini prompt + call + response parsing
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
└── README.md
```

---

## Setup

**Requirements:** Python 3.10+, a free [Gemini API key](https://aistudio.google.com/apikey).

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env and paste your GEMINI_API_KEY

python app.py
```

Open **http://localhost:5000** — Flask serves both the API and the
`frontend/` files, so there's nothing else to run.

---

## Using it

1. **Open a requisition** — paste a job title + full job description.
2. **Upload resumes** — drag in one or more PDF/DOCX/TXT files.
3. Each resume is parsed and scored against the job description; results
   appear as ranked candidate cards, best match first, each stamped with its
   score and a short justification.
4. Switch between requisitions with the dropdown; each keeps its own
   candidate list.

---

## The LLM prompt

`gemini_service.py` sends one system instruction + one user prompt per resume:

> *"You are an assistant that helps recruiters screen resumes. You will be
> given a candidate's resume text and a job description. Read both carefully,
> then respond with ONLY a JSON object matching this shape: candidate_name,
> skills[], experience_summary, education_summary, match_score (1–10),
> justification. Be specific in the justification: name the skills/experience
> that helped or hurt the score."*

followed by the actual `JOB DESCRIPTION` and `RESUME` text. The call sets
`response_mime_type: "application/json"` so Gemini returns parseable JSON
directly, with no markdown fences to strip.

---

## Notes / trade-offs

- **Scanned/image-only PDFs** aren't OCR'd — if `pdfplumber` can't extract
  text, the resume is skipped with a clear reason shown in the UI. Adding OCR
  (e.g. `pytesseract`) would be a natural next step.
- **Model name**: defaults to `gemini-flash-latest`; pin a specific version
  (e.g. `gemini-2.5-flash`) via `GEMINI_MODEL` in `.env` if you need
  reproducible scoring over time.
- **Auth**: intentionally left out — this is a local screening tool, not a
  multi-tenant product. Add Flask-Login or similar before deploying publicly.
- **Resume storage**: uploaded files are kept in `backend/uploads/` under a
  random filename; only extracted text is sent to Gemini.
