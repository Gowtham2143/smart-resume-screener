"""
Smart Resume Screener - Flask backend
Endpoints:
  POST   /api/jobs                     -> create a job posting
  GET    /api/jobs                     -> list job postings
  GET    /api/jobs/<job_id>            -> get one job posting
  POST   /api/jobs/<job_id>/resumes    -> upload one or more resumes, parse + score them
  GET    /api/jobs/<job_id>/candidates -> list scored candidates for a job, best first
  DELETE /api/jobs/<job_id>            -> delete a job and its candidates
"""
import os
import uuid

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

import database as db
from resume_parser import extract_text, SUPPORTED_EXTENSIONS
from gemini_service import evaluate_resume, GeminiError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend")

os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
CORS(app)
db.init_db()


# ---------- static frontend (so the whole thing runs from one server) ----------

@app.route("/")
def serve_index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:filename>")
def serve_frontend_assets(filename):
    if os.path.exists(os.path.join(FRONTEND_DIR, filename)):
        return send_from_directory(FRONTEND_DIR, filename)
    return jsonify({"error": "not found"}), 404


# ---------------------------------- jobs ----------------------------------

@app.route("/api/jobs", methods=["POST"])
def create_job():
    payload = request.get_json(silent=True) or {}
    title = (payload.get("title") or "").strip()
    description = (payload.get("description") or "").strip()

    if not title or not description:
        return jsonify({"error": "title and description are both required"}), 400

    job_id = db.create_job(title, description)
    return jsonify(db.get_job(job_id)), 201


@app.route("/api/jobs", methods=["GET"])
def list_jobs():
    return jsonify(db.list_jobs())


@app.route("/api/jobs/<job_id>", methods=["GET"])
def get_job(job_id):
    job = db.get_job(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    return jsonify(job)


@app.route("/api/jobs/<job_id>", methods=["DELETE"])
def delete_job(job_id):
    if not db.get_job(job_id):
        return jsonify({"error": "job not found"}), 404
    db.delete_job(job_id)
    return jsonify({"status": "deleted"})


# -------------------------------- resumes ----------------------------------

@app.route("/api/jobs/<job_id>/resumes", methods=["POST"])
def upload_resumes(job_id):
    job = db.get_job(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404

    files = request.files.getlist("resumes")
    if not files:
        return jsonify({"error": "attach at least one resume under the 'resumes' field"}), 400

    results = []
    for file in files:
        if not file or not file.filename:
            continue

        original_name = secure_filename(file.filename)
        ext = os.path.splitext(original_name)[1].lower()

        if ext not in SUPPORTED_EXTENSIONS:
            results.append({
                "filename": original_name,
                "status": "skipped",
                "reason": f"unsupported file type '{ext}'. Use PDF, DOCX or TXT.",
            })
            continue

        stored_name = f"{uuid.uuid4().hex}{ext}"
        stored_path = os.path.join(UPLOAD_DIR, stored_name)
        file.save(stored_path)

        try:
            resume_text = extract_text(stored_path, ext)
        except Exception as exc:
            results.append({"filename": original_name, "status": "error", "reason": f"could not read file: {exc}"})
            continue

        if not resume_text or len(resume_text.strip()) < 30:
            results.append({
                "filename": original_name,
                "status": "error",
                "reason": "no readable text found in this file (is it a scanned image?)",
            })
            continue

        try:
            evaluation = evaluate_resume(resume_text, job["description"])
        except GeminiError as exc:
            results.append({"filename": original_name, "status": "error", "reason": str(exc)})
            continue

        candidate_id = db.add_candidate(
            job_id=job_id,
            filename=original_name,
            stored_path=stored_name,
            raw_text=resume_text,
            evaluation=evaluation,
        )
        candidate = db.get_candidate(candidate_id)
        candidate["status"] = "scored"
        results.append(candidate)

    return jsonify({"results": results}), 201


@app.route("/api/jobs/<job_id>/candidates", methods=["GET"])
def list_candidates(job_id):
    if not db.get_job(job_id):
        return jsonify({"error": "job not found"}), 404
    return jsonify(db.list_candidates(job_id))


@app.route("/api/candidates/<candidate_id>", methods=["DELETE"])
def delete_candidate(candidate_id):
    db.delete_candidate(candidate_id)
    return jsonify({"status": "deleted"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
