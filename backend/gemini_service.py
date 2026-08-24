"""
Talks to the Gemini API to do two jobs in a single call:
  1. Extract structured data from the resume (name, skills, experience, education)
  2. Score how well the resume fits the job description, with a written justification

Combining both into one prompt keeps this to one API call per resume instead of two.
"""
import json
import os

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")

SYSTEM_INSTRUCTION = """You are an assistant that helps recruiters screen resumes.
You will be given a candidate's resume text and a job description.
Read both carefully, then respond with ONLY a JSON object (no markdown fences,
no commentary) matching exactly this shape:

{
  "candidate_name": string,            // best guess at the candidate's full name, or "Unknown"
  "skills": string[],                  // 5-15 concrete skills/technologies found in the resume
  "experience_summary": string,        // 2-3 sentences summarizing relevant work experience
  "education_summary": string,         // 1-2 sentences summarizing education
  "match_score": integer,              // 1-10, how well this resume fits the job description
  "justification": string              // 2-4 sentences explaining the score, citing specifics
}

Scoring guide:
  8-10 = strong match on required skills and experience level
  5-7  = partial match, meets some requirements but has notable gaps
  1-4  = weak match, missing most core requirements
Be specific in the justification: name the skills/experience that helped or hurt the score.
"""


class GeminiError(Exception):
    """Raised when the Gemini API call fails or returns something we can't use."""


def _get_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise GeminiError(
            "GEMINI_API_KEY is not set. Add it to backend/.env (see .env.example)."
        )
    return genai.Client(api_key=api_key)


def evaluate_resume(resume_text, job_description):
    client = _get_client()

    prompt = (
        f"JOB DESCRIPTION:\n{job_description}\n\n"
        f"RESUME:\n{resume_text[:12000]}"  # guard against extremely long resumes
    )

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )
    except Exception as exc:
        raise GeminiError(f"Gemini API request failed: {exc}") from exc

    raw_text = (response.text or "").strip()
    if not raw_text:
        raise GeminiError("Gemini returned an empty response.")

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise GeminiError(f"Gemini response was not valid JSON: {exc}") from exc

    return _normalize(data)


def _normalize(data):
    score = data.get("match_score")
    try:
        score = max(1, min(10, int(score)))
    except (TypeError, ValueError):
        score = 1

    skills = data.get("skills") or []
    if not isinstance(skills, list):
        skills = [str(skills)]

    return {
        "candidate_name": (data.get("candidate_name") or "Unknown").strip(),
        "skills": [str(s).strip() for s in skills if str(s).strip()][:15],
        "experience_summary": (data.get("experience_summary") or "").strip(),
        "education_summary": (data.get("education_summary") or "").strip(),
        "match_score": score,
        "justification": (data.get("justification") or "").strip(),
    }
