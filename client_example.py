#!/usr/bin/env python3
"""
Contoh Client — News Breaking Video API
Jalankan: python client_example.py
"""

import base64
from pathlib import Path

import httpx

API_URL = "http://localhost:8001"


def encode_file(path: str) -> str:
    """Encode file lokal ke base64 string."""
    return base64.b64encode(Path(path).read_bytes()).decode()


def generate_video(
    judul: str,
    isi: str,
    bg_video_path: str = None,    # path ke file MP4/WebM lokal (opsional)
    audio_path: str = None,       # path ke file MP3/WAV lokal (opsional)
    image_path: str = None,       # path ke file gambar lokal (opsional)
    output_path: str = "output.mp4",
    **kwargs,                     # config tambahan (lihat VideoRequest)
) -> dict:
    """
    Kirim request ke API dan simpan video ke file lokal.

    Returns:
        dict dengan kunci: title, summary, mime, duration, video_b64
    """
    payload = {"judul": judul, "isi": isi, **kwargs}

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
    print(f"   Judul   : {judul}")
    print(f"   Durasi  : {payload.get('duration', 7)} detik")

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
    generate_video(
        judul="Breaking News: Contoh Judul",
        isi="Ini teks ringkasan yang akan ditampilkan di video berita vertical.",
        output_path="output_simple.mp4",
        watermark="@myaccount",
        accent_color="#FF0000",
        title_bg_color="#FFFFFF",
        duration=7,
    )

    # ── Contoh 2: Dengan video BG + audio + gambar ──────────────────────────
    # Uncomment dan sesuaikan path jika ada file lokal:
    #
    # generate_video(
    #     judul="Headline Berita",
    #     isi="Ringkasan dua kalimat untuk video.",
    #     bg_video_path="bg.mp4",
    #     audio_path="music.mp3",
    #     image_path="foto.jpg",
    #     output_path="output_full.mp4",
    #     watermark="@medianame",
    #     accent_color="#FF6600",
    #     title_bg_color="#FFFFFF",
    #     title_y=1300,
    #     summary_y=1600,
    # )
