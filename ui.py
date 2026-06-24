#!/usr/bin/env python3
"""
News Breaking Video — Flask UI
==============================
UI sederhana yang memanggil API FastAPI di main.py (`POST /generate-video`).

Jalankan:
    1) Terminal 1 → python main.py           (FastAPI, port 8000)
    2) Terminal 2 → python ui.py             (Flask UI, port 5000)
    3) Buka       → http://localhost:5000
"""

import base64
import os
import uuid
from pathlib import Path

import httpx
from flask import Flask, jsonify, render_template, request, send_from_directory

# ─── Konfigurasi ───────────────────────────────────────────────────────────────
API_URL        = os.getenv("API_URL", "http://localhost:8000")
HOST           = os.getenv("UI_HOST", "0.0.0.0")
PORT           = int(os.getenv("UI_PORT", "5000"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OUTPUT_DIR = Path(__file__).parent / "static" / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_MB = 64  # batas total upload (BG video + audio + image)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024


# ─── Util ──────────────────────────────────────────────────────────────────────
def file_to_b64(file_storage) -> str | None:
    """werkzeug FileStorage → base64 string (None bila kosong)."""
    if not file_storage or file_storage.filename == "":
        return None
    return base64.b64encode(file_storage.read()).decode()


def form_int(name: str, default: int) -> int:
    try:
        return int(request.form.get(name, default))
    except (TypeError, ValueError):
        return default


def form_str(name: str, default: str) -> str:
    val = request.form.get(name)
    return val if val not in (None, "") else default


def form_pos(name: str, default: int):
    """
    Return 'auto' bila auto-layout aktif atau field kosong/berisi 'auto',
    selainnya kembalikan int.
    """
    if request.form.get("auto_layout") == "on":
        return "auto"
    raw = (request.form.get(name) or "").strip().lower()
    if raw in ("", "auto"):
        return "auto"
    try:
        return int(raw)
    except ValueError:
        return default


# ─── Routes ────────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", api_url=API_URL)


@app.route("/api/generate", methods=["POST"])
def generate():
    """
    Terima form-data dari UI, encode file → base64,
    teruskan ke FastAPI, simpan MP4 hasil, balas URL preview.
    """
    article_url = (request.form.get("url") or "").strip()
    if not article_url:
        return jsonify({"error": "URL artikel wajib diisi."}), 400

    gemini_key = (request.form.get("gemini_api_key") or GEMINI_API_KEY or "").strip()
    if not gemini_key:
        return jsonify({
            "error": "GEMINI_API_KEY wajib diisi (set env GEMINI_API_KEY atau kirim lewat form).",
        }), 400

    payload: dict = {
        "gemini_api_key": gemini_key,
        "url":                article_url,
        "watermark":          form_str("watermark", "@username"),
        "language":           form_str("language", "Indonesia"),
        "duration":           form_int("duration", 7),
        "accent_color":       form_str("accent_color", "#FF0000"),
        "title_bg_color":     form_str("title_bg_color", "#FFFFFF"),
        "title_text_color":   form_str("title_text_color", "#000000"),
        "summary_text_color": form_str("summary_text_color", "#FFFFFF"),
        "canvas_bg_color":    form_str("canvas_bg_color", "#000000"),
        "image_x":            form_pos("image_x",   0),
        "image_y":            form_pos("image_y",   0),
        "title_x":            form_pos("title_x",   80),
        "title_y":            form_pos("title_y",   1250),
        "summary_x":          form_pos("summary_x", 80),
        "summary_y":          form_pos("summary_y", 1580),
    }

    bg_b64    = file_to_b64(request.files.get("bg_video"))
    audio_b64 = file_to_b64(request.files.get("audio"))
    image_b64 = file_to_b64(request.files.get("image"))
    if bg_b64:    payload["bg_video_b64"] = bg_b64
    if audio_b64: payload["audio_b64"]    = audio_b64
    if image_b64: payload["image_b64"]    = image_b64

    try:
        with httpx.Client(timeout=180) as client:
            resp = client.post(f"{API_URL}/generate-video", json=payload)
    except httpx.RequestError as e:
        return jsonify({"error": f"Tidak dapat terhubung ke API ({API_URL}): {e}"}), 502

    if resp.status_code != 200:
        return jsonify({
            "error":  f"API mengembalikan status {resp.status_code}",
            "detail": resp.text[:1000],
        }), resp.status_code

    data = resp.json()

    filename = f"video_{uuid.uuid4().hex}.mp4"
    out_path = OUTPUT_DIR / filename
    out_path.write_bytes(base64.b64decode(data["video_b64"]))

    return jsonify({
        "title":     data.get("title", ""),
        "summary":   data.get("summary", ""),
        "duration":  data.get("duration", payload["duration"]),
        "video_url": f"/static/outputs/{filename}",
        "size_mb":   round(out_path.stat().st_size / (1024 * 1024), 2),
    })


@app.route("/static/outputs/<path:filename>")
def serve_output(filename: str):
    return send_from_directory(OUTPUT_DIR, filename, conditional=True)


@app.errorhandler(413)
def too_large(_e):
    return jsonify({"error": f"Total upload melebihi batas {MAX_UPLOAD_MB} MB."}), 413


# ─── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"🚀 Flask UI  : http://{HOST}:{PORT}")
    print(f"🔗 API target: {API_URL}")
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host=HOST, port=PORT, debug=debug)
