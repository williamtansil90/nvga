# News Breaking Video API 🎬

Konversi URL artikel berita → video vertical 9:16 siap upload media sosial.

```
URL Artikel + BG Video + Audio  →  POST /generate-video  →  Base64 MP4
```

---

## Docker (disarankan untuk deploy)

```bash
cp .env.example .env
# Edit .env → isi GEMINI_API_KEY=AIza...

docker compose up -d --build
```

| Service | URL |
|---|---|
| Web UI | http://localhost:5000 |
| API + Swagger | http://localhost:8000/docs |

Perintah berguna:

```bash
docker compose logs -f      # lihat log
docker compose down         # stop
docker compose up -d --build  # rebuild setelah pull/update
```

---

## Instalasi (tanpa Docker)

```bash
pip install -r requirements.txt
```

> **Prasyarat sistem:** `ffmpeg` harus terinstall
> - Ubuntu/Debian: `sudo apt install ffmpeg`
> - macOS: `brew install ffmpeg`

---

## Menjalankan Server

```bash
export GEMINI_API_KEY="AIza..."

python main.py
# atau
uvicorn main:app --host 0.0.0.0 --port 8000
```

Swagger UI tersedia di: http://localhost:8000/docs

---

## Penggunaan API

### `POST /generate-video`

**Request Body (JSON):**

| Field | Tipe | Wajib | Default | Keterangan |
|---|---|---|---|---|
| `url` | string | ✅ | — | URL artikel berita |
| `bg_video_b64` | string | ❌ | null | Video latar (MP4/WebM) base64 |
| `audio_b64` | string | ❌ | null | Audio (MP3/WAV/AAC) base64 |
| `image_b64` | string | ❌ | null | Override gambar artikel base64 |
| `watermark` | string | ❌ | `@username` | Teks watermark |
| `language` | string | ❌ | `Indonesia` | Bahasa output Gemini |
| `duration` | int | ❌ | `7` | Durasi video (3–60 detik) |
| `accent_color` | string | ❌ | `#FF0000` | Warna aksen + gradasi |
| `title_bg_color` | string | ❌ | `#FFFFFF` | Warna kotak judul |
| `title_text_color` | string | ❌ | `#000000` | Warna teks judul |
| `summary_text_color` | string | ❌ | `#FFFFFF` | Warna teks ringkasan |
| `canvas_bg_color` | string | ❌ | `#000000` | Warna background (tanpa video) |
| `image_x` | int | ❌ | `0` | Posisi X foto artikel |
| `image_y` | int | ❌ | `0` | Posisi Y foto artikel |
| `title_x` | int | ❌ | `80` | Posisi X kotak judul |
| `title_y` | int | ❌ | `1250` | Posisi Y kotak judul |
| `summary_x` | int | ❌ | `80` | Posisi X ringkasan |
| `summary_y` | int | ❌ | `1580` | Posisi Y ringkasan |

**Response (JSON):**
```json
{
  "video_b64": "AAAAIGZ0eXBpc29tAAACAGlzb21...",
  "title": "Judul berita yang diekstrak",
  "summary": "Ringkasan 2 kalimat dari Gemini.",
  "mime": "video/mp4",
  "duration": 7
}
```

---

## Contoh: cURL

```bash
# Request minimal (hanya URL)
curl -X POST http://localhost:8000/generate-video \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.cnnindonesia.com/",
    "watermark": "@akunsaya",
    "language": "Indonesia",
    "accent_color": "#FF0000"
  }' \
  | python3 -c "
import sys, json, base64
data = json.load(sys.stdin)
print('Judul:', data['title'])
open('output.mp4', 'wb').write(base64.b64decode(data['video_b64']))
print('Video disimpan: output.mp4')
"
```

## Contoh: Python dengan BG Video + Audio

```python
import base64, httpx

def enc(path): return base64.b64encode(open(path,'rb').read()).decode()

resp = httpx.post("http://localhost:8000/generate-video", json={
    "url":          "https://www.detik.com/",
    "bg_video_b64": enc("background.mp4"),   # opsional
    "audio_b64":    enc("music.mp3"),        # opsional
    "watermark":    "@mediasaya",
    "language":     "Indonesia",
    "accent_color": "#FF6600",
    "duration":     10,
}, timeout=120)

data = resp.json()
print("Judul:", data["title"])
open("hasil.mp4", "wb").write(base64.b64decode(data["video_b64"]))
```

---

## Arsitektur Proses

```
URL Artikel
    │
    ├─► Gemini AI ──────────────────► Judul + Ringkasan
    │                                         │
    └─► Scrape og:image ──────────────► Gambar Artikel
                                              │
                                              ▼
                                     PIL Render Overlay (PNG RGBA)
                                      • Foto + Shadow
                                      • Gradient aksen
                                      • Garis pemisah
                                      • Kotak judul
                                      • Teks ringkasan
                                      • Watermark
                                              │
                                    ┌─────────┴─────────┐
                                 BG Video            Warna Solid
                                    └─────────┬─────────┘
                                              │
                                         FFmpeg
                                      • Composite overlay
                                      • Progress bar animasi
                                      • Mix audio
                                      • Encode H.264 MP4
                                              │
                                         Base64 MP4 ◄── Response
```

---

## Output Spesifikasi

| Parameter | Nilai |
|---|---|
| Resolusi | 1080 × 1920 px (9:16) |
| Codec video | H.264 (libx264) |
| Codec audio | AAC 192kbps |
| Frame rate | 30 fps |
| Format | MP4 (yuv420p) |
