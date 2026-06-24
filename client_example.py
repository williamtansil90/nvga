#!/usr/bin/env python3
"""
Contoh Client — News Breaking Video API
Jalankan: python client_example.py
"""

import base64
import json
import sys
from pathlib import Path

import httpx

API_URL = "http://localhost:8000"


def encode_file(path: str) -> str:
    """Encode file lokal ke base64 string."""
    return base64.b64encode(Path(path).read_bytes()).decode()


def generate_video(
    article_url: str,
    bg_video_path: str = None,    # path ke file MP4/WebM lokal (opsional)
    audio_path: str = None,       # path ke file MP3/WAV lokal (opsional)
    image_path: str = None,       # path ke file gambar lokal (opsional override)
    output_path: str = "output.mp4",
    **kwargs,                     # config tambahan (lihat VideoRequest)
) -> dict:
    """
    Kirim request ke API dan simpan video ke file lokal.

    Returns:
        dict dengan kunci: title, summary, mime, duration, video_b64
    """
    payload = {"url": article_url, **kwargs}

    if bg_video_path:
        payload["bg_video_b64"] = encode_file(bg_video_path)
        print(f"  ✓ BG video di-encode: {bg_video_path}")

    if audio_path:
        payload["audio_b64"] = encode_file(audio_path)
        print(f"  ✓ Audio di-encode:   {audio_path}")

    if image_path:
        payload["image_b64"] = encode_file(image_path)
        print(f"  ✓ Gambar di-encode:  {image_path}")

    print(f"\n🚀 Mengirim ke {API_URL}/generate-video ...")
    print(f"   URL Artikel : {article_url}")
    print(f"   Bahasa      : {payload.get('language', 'Indonesia')}")
    print(f"   Durasi      : {payload.get('duration', 7)} detik")

    with httpx.Client(timeout=120) as client:
        resp = client.post(f"{API_URL}/generate-video", json=payload)
        resp.raise_for_status()
        data = resp.json()

    print(f"\n✅ Berhasil!")
    print(f"   Judul   : {data['title']}")
    print(f"   Ringkasan: {data['summary'][:80]}...")

    video_bytes = base64.b64decode(data["video_b64"])
    Path(output_path).write_bytes(video_bytes)
    size_mb = len(video_bytes) / (1024 * 1024)
    print(f"   Video   : {output_path} ({size_mb:.2f} MB)")

    return data


# ─── Contoh Penggunaan ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    # ── Contoh 1: Hanya URL, background hitam (paling sederhana) ──────────
    generate_video(
        article_url="https://www.cnnindonesia.com/",
        output_path="output_simple.mp4",
        watermark="@myaccount",
        language="Indonesia",
        accent_color="#FF0000",
        title_bg_color="#FFFFFF",
        duration=7,
    )

    # ── Contoh 2: Dengan video BG + audio ─────────────────────────────────
    # Uncomment dan sesuaikan path jika ada file lokal:
    #
    # generate_video(
    #     article_url="https://www.cnnindonesia.com/",
    #     bg_video_path="bg.mp4",          # file video latar
    #     audio_path="music.mp3",          # musik latar
    #     output_path="output_full.mp4",
    #     watermark="@medianame",
    #     language="Indonesia",
    #     accent_color="#FF6600",
    #     title_bg_color="#FFFFFF",
    #     title_y=1300,
    #     summary_y=1600,
    # )
