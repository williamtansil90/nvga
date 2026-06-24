# n8n → News Breaking Video API

## Impor workflow

1. Buka n8n → **Workflows** → menu **⋯** → **Import from File**.
2. Pilih `workflow-generate-video.json` di folder ini.

## Yang perlu diubah

- Node **POST /generate-video**: ganti `http://127.0.0.1:8000/generate-video` ke URL server Anda (mis. `https://api.domain.com/generate-video`) jika FastAPI tidak di mesin yang sama dengan n8n.
- Node **Payload (edit di sini)**: ubah `url`, `duration`, `watermark`.

Pastikan service `n2v-api` (port **8000**) sudah jalan sebelum menjalankan workflow.

## Response

Body JSON berisi antara lain:

- `video_b64` — string base64 MP4 (besar).
- `title`, `summary`, `duration`, `mime`.

Untuk simpan file MP4 di n8n, tambahkan node **Move Binary Data** atau **Write Binary File** setelah HTTP Request (decode `video_b64` → binary). Atau proses di node **Code** dengan `Buffer.from($json.video_b64, 'base64')`.

## Contoh body JSON lengkap (referensi)

Semua field opsional kecuali `url`. Tanpa `bg_video_b64` / `audio_b64`, backend memakai `media/background-video.mp4` dan `media/music.mp3`.

```json
{
  "url": "https://www.cnnindonesia.com/nasional/berita-123",
  "watermark": "@channel",
  "language": "Indonesia",
  "duration": 7,
  "accent_color": "#FF0000",
  "title_bg_color": "#FFFFFF",
  "title_text_color": "#000000",
  "summary_text_color": "#FFFFFF",
  "canvas_bg_color": "#000000",
  "image_x": "auto",
  "image_y": "auto",
  "title_x": "auto",
  "title_y": "auto",
  "summary_x": "auto",
  "summary_y": "auto",
  "bg_video_b64": null,
  "audio_b64": null,
  "image_b64": null
}
```

Media base64 (opsional): isi string base64 file MP4/WebM/MP3/JPEG tanpa atau dengan prefix `data:...;base64,`.

## Node HTTP Request saja (tanpa impor file)

1. Tambah node **HTTP Request**.
2. **Method**: `POST`
3. **URL**: `http://ALAMAT-API:8000/generate-video`
4. **Authentication**: None (atau sesuai kebutuhan Anda)
5. **Send Body**: ON → **Body Content Type**: JSON
6. **Specify Body**: Using JSON / JSON (tergantung versi n8n)
7. Isi body, misalnya mode **Expression**:

```javascript
{{ JSON.stringify({
  url: "https://www.cnnindonesia.com/",
  duration: 7,
  watermark: "@n8n",
  language: "Indonesia"
}) }}
```

8. **Options** → **Timeout**: `300000` (5 menit), karena Gemini + FFmpeg bisa lama.

## Curl setara

```bash
curl -sS -X POST "http://127.0.0.1:8000/generate-video" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.cnnindonesia.com/","duration":7,"watermark":"@n8n"}' \
  --max-time 300
```
