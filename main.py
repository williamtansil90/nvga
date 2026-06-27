#!/usr/bin/env python3
"""
News Breaking Video API
======================
POST /generate-video  →  base64 MP4

Input  : judul, isi, base64 video BG, base64 audio, konfigurasi warna/posisi
Output : base64 MP4 + judul + ringkasan
"""

import asyncio
import base64
import binascii
import io
import json
import os
import shutil
import subprocess
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, Union

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from pydantic import BaseModel, Field, field_validator

try:
    LANCZOS = Image.Resampling.LANCZOS
except AttributeError:
    LANCZOS = Image.LANCZOS

# ─── App ───────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Validasi dependensi sistem saat startup."""
    if shutil.which("ffmpeg") is None:
        print(
            "PERINGATAN: `ffmpeg` tidak ditemukan di PATH. "
            "Endpoint /generate-video akan gagal sampai ffmpeg dipasang."
        )
    print(f"Default BG video: {DEFAULT_BG_VIDEO} "
          f"({'OK' if DEFAULT_BG_VIDEO.is_file() else 'tidak ditemukan'})")
    print(f"Default audio   : {DEFAULT_AUDIO} "
          f"({'OK' if DEFAULT_AUDIO.is_file() else 'tidak ditemukan'})")
    yield


app = FastAPI(
    title="News Breaking Video API",
    description="Ubah judul + isi → video editan 9:16 siap media sosial (base64 MP4)",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Konstanta ─────────────────────────────────────────────────────────────────
def _load_dotenv() -> None:
    env_path = Path(__file__).parent / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip("\"'"))


_load_dotenv()
DURATION_SEC   = 7
FPS            = 30
CANVAS_W       = 1080
CANVAS_H       = 1920
ARTICLE_IMG_W  = 850   # lebar foto artikel di canvas

FONT_BOLD       = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_ITALIC     = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"
FONT_REGULAR    = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# ─── Aset Default ─────────────────────────────────────────────────────────────
# Dipakai bila request tidak menyertakan bg_video_b64 / audio_b64.
# Bisa dimatikan dengan env var BG_VIDEO_DEFAULT="" / AUDIO_DEFAULT="".
MEDIA_DIR = Path(__file__).parent / "media"
DEFAULT_BG_VIDEO = Path(os.getenv("BG_VIDEO_DEFAULT", str(MEDIA_DIR / "background-video.mp4")))
DEFAULT_AUDIO    = Path(os.getenv("AUDIO_DEFAULT",    str(MEDIA_DIR / "music.mp3")))

# ─── Skema Pydantic ────────────────────────────────────────────────────────────
class VideoRequest(BaseModel):
    # ── Wajib ──
    judul: str = Field(..., description="Judul berita / headline video")
    isi:   str = Field(..., description="Isi / ringkasan teks yang ditampilkan di video")

    # ── Media (opsional, base64 dengan/tanpa data-URL prefix) ──
    bg_video_b64: Optional[str] = Field(None, description="Video latar (MP4/WebM) di-encode base64")
    audio_b64:    Optional[str] = Field(None, description="Audio (MP3/WAV/AAC) di-encode base64")
    image_b64:    Optional[str] = Field(None, description="Gambar artikel (JPEG/PNG) di-encode base64")

    # ── Konfigurasi teks ──
    watermark:  str = Field("@username",  description="Teks watermark di bawah video")
    duration:   int = Field(7,            ge=3, le=60, description="Durasi video (detik)")

    # ── Warna ──
    accent_color:       str = Field("#FF0000", description="Warna aksen (garis + gradasi)")
    title_bg_color:     str = Field("#FFFFFF", description="Warna kotak judul")
    title_text_color:   str = Field("#000000", description="Warna teks judul")
    summary_text_color: str = Field("#FFFFFF", description="Warna teks ringkasan")
    canvas_bg_color:    str = Field("#000000", description="Warna background (jika tanpa video)")

    # ── Posisi elemen (koordinat canvas 1080×1920; bisa int atau "auto") ──
    image_x:   Union[int, str] = Field("auto", description="Posisi X foto artikel — int atau 'auto'")
    image_y:   Union[int, str] = Field("auto", description="Posisi Y foto artikel — int atau 'auto'")
    title_x:   Union[int, str] = Field("auto", description="Posisi X kotak judul — int atau 'auto'")
    title_y:   Union[int, str] = Field("auto", description="Posisi Y kotak judul — int atau 'auto'")
    summary_x: Union[int, str] = Field("auto", description="Posisi X ringkasan — int atau 'auto'")
    summary_y: Union[int, str] = Field("auto", description="Posisi Y ringkasan — int atau 'auto'")

    @field_validator("judul", "isi", mode="before")
    @classmethod
    def _normalize_text(cls, v):
        if v is None or not str(v).strip():
            raise ValueError("judul dan isi wajib diisi")
        return str(v).strip()

    @field_validator("image_x", "image_y", "title_x", "title_y",
                     "summary_x", "summary_y", mode="before")
    @classmethod
    def _normalize_pos(cls, v):
        """Terima int, 'auto', atau string numerik ('100')."""
        if v is None:
            return "auto"
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("", "auto"):
                return "auto"
            try:
                return int(s)
            except ValueError as e:
                raise ValueError(f"Harus int atau 'auto', dapat: {v!r}") from e
        return int(v)


class VideoResponse(BaseModel):
    video_b64: str = Field(..., description="Video MP4 hasil di-encode base64")
    title:     str = Field(..., description="Judul dari input")
    summary:   str = Field(..., description="Isi dari input")
    mime:      str = Field("video/mp4")
    duration:  int


# ─── Utilitas ──────────────────────────────────────────────────────────────────
def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """'#RRGGBB'  atau  '#RGB'  →  (r, g, b)"""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def decode_b64(data: Optional[str]) -> Optional[bytes]:
    """Hapus prefix data-URL jika ada, lalu decode base64."""
    if not data:
        return None
    if isinstance(data, str):
        stripped = data.strip()
        if stripped.lower() in ("", "string", "number", "boolean", "integer"):
            return None
    if "," in data:
        data = data.split(",", 1)[1]
    try:
        return base64.b64decode(data, validate=False)
    except (ValueError, binascii.Error):
        return None


def probe_streams(path: Path) -> dict[str, bool]:
    """Deteksi stream video/audio di file media."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError:
        return {"has_video": False, "has_audio": False}
    if result.returncode != 0:
        return {"has_video": False, "has_audio": False}
    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return {"has_video": False, "has_audio": False}
    types = {stream.get("codec_type") for stream in data.get("streams", [])}
    return {"has_video": "video" in types, "has_audio": "audio" in types}


DEBUG_LOG = "/home/ubuntu/py/ve/.cursor/debug-920558.log"


def _debug_log(location, message, data, hypothesis_id="F"):
    # #region agent log
    try:
        import time

        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "sessionId": "920558",
                        "timestamp": int(time.time() * 1000),
                        "location": location,
                        "message": message,
                        "data": data,
                        "hypothesisId": hypothesis_id,
                        "runId": "post-fix",
                    }
                )
                + "\n"
            )
    except OSError:
        pass
    # #endregion


def resolve_bg_video_path(req: VideoRequest, tmpdir: Path) -> Optional[Path]:
    if req.bg_video_b64:
        candidate = tmpdir / "bg_video.mp4"
        raw = decode_b64(req.bg_video_b64)
        if raw:
            candidate.write_bytes(raw)
            streams = probe_streams(candidate)
            _debug_log(
                "main.py:resolve_bg_video_path",
                "Probed uploaded bg media",
                {"size": len(raw), **streams},
                "F",
            )
            if streams["has_video"]:
                return candidate
            _debug_log(
                "main.py:resolve_bg_video_path",
                "Uploaded bg has no video stream; using default",
                {"fallback": str(DEFAULT_BG_VIDEO)},
                "F",
            )
    if DEFAULT_BG_VIDEO.is_file() and probe_streams(DEFAULT_BG_VIDEO)["has_video"]:
        return DEFAULT_BG_VIDEO
    return None


def resolve_audio_path(req: VideoRequest, tmpdir: Path) -> Optional[Path]:
    if req.audio_b64:
        candidate = tmpdir / "audio"
        raw = decode_b64(req.audio_b64)
        if raw:
            candidate.write_bytes(raw)
            streams = probe_streams(candidate)
            _debug_log(
                "main.py:resolve_audio_path",
                "Probed uploaded audio media",
                {"size": len(raw), **streams},
                "F",
            )
            if streams["has_audio"]:
                return candidate
            _debug_log(
                "main.py:resolve_audio_path",
                "Uploaded audio has no audio stream; using default",
                {"fallback": str(DEFAULT_AUDIO)},
                "F",
            )
    if DEFAULT_AUDIO.is_file() and probe_streams(DEFAULT_AUDIO)["has_audio"]:
        return DEFAULT_AUDIO
    return None


def load_font(size: int, bold: bool = False, italic: bool = False):
    """Muat font TrueType; fallback ke default bila file tidak ditemukan."""
    path = FONT_BOLD if bold else (FONT_ITALIC if italic else FONT_REGULAR)
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()


def wrap_text_lines(draw: ImageDraw.ImageDraw, text: str, font, max_px: int) -> list[str]:
    """Word-wrap teks agar masuk dalam max_px."""
    words = text.split()
    lines, buf = [], ""
    for word in words:
        test = f"{buf} {word}".strip()
        if draw.textlength(test, font=font) <= max_px:
            buf = test
        else:
            if buf:
                lines.append(buf)
            buf = word
    if buf:
        lines.append(buf)
    return lines or [""]


# ─── Auto Layout ───────────────────────────────────────────────────────────────
# Konstanta tata letak. Diatur supaya gambar terpusat, judul+ringkasan tidak
# masuk ke area watermark/progress bar di bawah, dan tidak tumpang tindih.
SAFE_TOP        = 80     # margin atas
SAFE_BOTTOM     = 200    # margin bawah (watermark di y=1840, progress bar y=1850)
GAP_IMG_TITLE   = 60     # jarak gambar → kotak judul (sudah termasuk garis aksen)
GAP_TITLE_SUM   = 50     # jarak kotak judul → ringkasan
MIN_IMG_HEIGHT  = 380    # batas bawah saat auto-resize gambar agar konten muat

# Tinggi blok internal yang harus sinkron dengan render_overlay():
TITLE_LINE_H    = 75
TITLE_PADDING   = 40
SUMMARY_LINE_H  = 50


def _measure_wrap_lines(text: str, font, max_w: int) -> int:
    """Hitung jumlah baris setelah word-wrap (tanpa render)."""
    if not text or not text.strip():
        return 0
    tmp = Image.new("RGBA", (1, 1))
    return len(wrap_text_lines(ImageDraw.Draw(tmp), text, font, max_w))


def _measure_article_image(article_image_bytes: Optional[bytes]) -> tuple[int, int]:
    """Hitung (iw, ih) gambar artikel pada lebar ARTICLE_IMG_W."""
    if not article_image_bytes:
        return 0, 0
    try:
        img = Image.open(io.BytesIO(article_image_bytes))
        if img.width <= 0 or img.height <= 0:
            return 0, 0
        aspect = img.width / img.height
        iw = ARTICLE_IMG_W
        ih = max(1, int(iw / aspect))
        return iw, ih
    except Exception:
        return 0, 0


def compute_layout(
    article_image_bytes: Optional[bytes],
    title: str,
    summary: str,
    req: VideoRequest,
) -> dict:
    """
    Susun posisi elemen secara seimbang & tidak tumpang tindih.
    Field req yang bernilai "auto" akan diisi otomatis; selainnya dihormati.
    """
    W, H = CANVAS_W, CANVAS_H

    iw, ih = _measure_article_image(article_image_bytes)

    n_title   = _measure_wrap_lines(title,   load_font(58, bold=True),  W - 200)
    n_summary = _measure_wrap_lines(summary, load_font(36, italic=True), W - 200)
    title_box_h = (n_title * TITLE_LINE_H + TITLE_PADDING * 2) if n_title else 0
    summary_h   = n_summary * SUMMARY_LINE_H

    def total_height(image_h: int) -> int:
        h, prev = 0, None
        for kind, val in [("img", image_h), ("title", title_box_h), ("sum", summary_h)]:
            if val <= 0:
                continue
            if prev is not None:
                h += GAP_IMG_TITLE if prev == "img" else GAP_TITLE_SUM
            h += val
            prev = kind
        return h

    avail_h = H - SAFE_TOP - SAFE_BOTTOM
    total_h = total_height(ih)

    # Skala gambar artikel turun bila konten kepenuhan
    if total_h > avail_h and ih > 0:
        non_image_h = total_h - ih
        target_image_h = max(MIN_IMG_HEIGHT, avail_h - non_image_h)
        if target_image_h < ih:
            scale = target_image_h / ih
            iw = max(1, int(iw * scale))
            ih = target_image_h
            total_h = total_height(ih)

    start_y = SAFE_TOP + max(0, (avail_h - total_h) // 2)

    cur_y = start_y
    auto_image_y = 0
    auto_title_y = 0
    auto_summary_y = 0
    prev = None

    if ih > 0:
        auto_image_y = cur_y
        cur_y += ih
        prev = "img"
    if title_box_h > 0:
        if prev is not None:
            cur_y += GAP_IMG_TITLE if prev == "img" else GAP_TITLE_SUM
        auto_title_y = cur_y
        cur_y += title_box_h
        prev = "title"
    if summary_h > 0:
        if prev is not None:
            cur_y += GAP_TITLE_SUM if prev == "title" else GAP_IMG_TITLE
        auto_summary_y = cur_y

    auto = {
        "image_x":   max(0, (W - iw) // 2) if iw > 0 else 0,
        "image_y":   auto_image_y,
        "title_x":   80,
        "title_y":   auto_title_y,
        "summary_x": 80,
        "summary_y": auto_summary_y,
    }

    def resolve(name: str) -> int:
        v = getattr(req, name)
        if isinstance(v, str) and v.strip().lower() == "auto":
            return auto[name]
        return int(v)

    return {
        "image_x":   resolve("image_x"),
        "image_y":   resolve("image_y"),
        "image_w":   iw,
        "image_h":   ih,
        "title_x":   resolve("title_x"),
        "title_y":   resolve("title_y"),
        "summary_x": resolve("summary_x"),
        "summary_y": resolve("summary_y"),
    }


# ─── Render overlay (PNG transparan 1080×1920) ─────────────────────────────────
def render_overlay(
    article_image_bytes: Optional[bytes],
    title: str,
    summary: str,
    req: VideoRequest,
    layout: dict,
) -> Image.Image:
    """
    Buat gambar PNG RGBA yang mereplikasi semua elemen visual dari
    aplikasi React (foto, gradient, garis, kotak judul, ringkasan, watermark).
    Progress bar akan ditambahkan oleh ffmpeg secara dinamis.
    """
    W, H = CANVAS_W, CANVAS_H
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")

    accent     = hex_to_rgb(req.accent_color)
    title_bg   = hex_to_rgb(req.title_bg_color)
    title_txt  = hex_to_rgb(req.title_text_color)
    summary_txt = hex_to_rgb(req.summary_text_color)

    # ── 1. Foto Artikel ───────────────────────────────────────────────────
    iw = int(layout.get("image_w", 0))
    ih = int(layout.get("image_h", 0))
    img_x = int(layout["image_x"])
    img_y = int(layout["image_y"])
    if article_image_bytes and iw > 0 and ih > 0:
        try:
            img = Image.open(io.BytesIO(article_image_bytes)).convert("RGBA")
            if img.width > 0 and img.height > 0:
                img = img.resize((iw, ih), LANCZOS)

                shadow_size = (iw + 60, ih + 60)
                shadow = Image.new("RGBA", shadow_size, (0, 0, 0, 0))
                sd = ImageDraw.Draw(shadow)
                sd.rectangle([30, 30, iw + 30, ih + 30], fill=(0, 0, 0, 130))
                shadow = shadow.filter(ImageFilter.GaussianBlur(20))

                sx = img_x - 30
                sy = img_y - 30
                overlay.alpha_composite(shadow, (max(sx, 0), max(sy, 0)))
                overlay.alpha_composite(img, (img_x, img_y))
        except Exception:
            pass  # lanjut tanpa gambar bila error

    # ── 2. Gradient Overlay ────────────────────────────────────────────────
    # Mereplikasi logika gradient JS (multi-stop):
    #   stop 0   → alpha 0.00
    #   stop 0.3 → alpha 0.60
    #   stop 0.7 → alpha 0.95
    #   stop 1   → alpha 1.00
    # Trik cepat: bangun kolom 1×grad_h lalu resize ke W×grad_h (O(grad_h) bukan O(W*grad_h)).
    grad_start_y = int(H * 0.5)
    grad_h = H - grad_start_y
    r, g, b = accent

    column_pixels = []
    for y in range(grad_h):
        t = y / max(grad_h - 1, 1)
        if t < 0.3:
            alpha = (t / 0.3) * 0.6
        elif t < 0.7:
            alpha = 0.6 + (t - 0.3) / 0.4 * 0.35
        else:
            alpha = 0.95 + (t - 0.7) / 0.3 * 0.05
        column_pixels.append((r, g, b, min(255, int(255 * alpha))))

    column = Image.new("RGBA", (1, grad_h))
    column.putdata(column_pixels)
    gradient = column.resize((W, grad_h), Image.NEAREST)
    overlay.alpha_composite(gradient, (0, grad_start_y))

    # ── 3. Garis Aksen + Kotak Judul ───────────────────────────────────────
    title_x = int(layout["title_x"])
    title_y = int(layout["title_y"])
    if title.strip():
        # Garis aksen di atas kotak judul
        lx, ly = title_x, title_y - 15
        draw.rectangle(
            [lx, ly, lx + (W - 160), ly + 12],
            fill=(*accent, 255),
        )

        font_title = load_font(58, bold=True)
        title_lines = wrap_text_lines(draw, title, font_title, W - 200)
        box_h = len(title_lines) * TITLE_LINE_H + TITLE_PADDING * 2
        box_w = W - 160

        draw.rectangle(
            [title_x, title_y, title_x + box_w, title_y + box_h],
            fill=(*title_bg, 255),
        )
        for i, line in enumerate(title_lines):
            ty = title_y + TITLE_PADDING + i * TITLE_LINE_H
            draw.text((title_x + TITLE_PADDING, ty), line, font=font_title, fill=(*title_txt, 255))

    # ── 4. Teks Ringkasan ──────────────────────────────────────────────────
    summary_x = int(layout["summary_x"])
    summary_y = int(layout["summary_y"])
    if summary.strip():
        font_summary = load_font(36, italic=True)
        sum_lines = wrap_text_lines(draw, summary, font_summary, W - 200)
        for i, line in enumerate(sum_lines):
            ty = summary_y + i * SUMMARY_LINE_H
            draw.text((summary_x + 2, ty + 2), line, font=font_summary, fill=(0, 0, 0, 140))
            draw.text((summary_x, ty), line, font=font_summary, fill=(*summary_txt, 255))

    # ── 5. Watermark ───────────────────────────────────────────────────────
    font_wm = load_font(32, bold=True)
    wm_w = draw.textlength(req.watermark, font=font_wm)
    wm_x = int((W - wm_w) / 2)
    wm_y = H - 80
    draw.text((wm_x + 2, wm_y + 2), req.watermark, font=font_wm, fill=(0, 0, 0, 150))
    draw.text((wm_x, wm_y), req.watermark, font=font_wm, fill=(255, 255, 255, 255))

    return overlay


# ─── Komposisi Video dengan FFmpeg ─────────────────────────────────────────────
def compose_video(
    overlay_path: Path,
    bg_video_path: Optional[Path],
    audio_path: Optional[Path],
    canvas_bg: str,
    output_path: Path,
    duration: int = DURATION_SEC,
    fps: int = FPS,
) -> None:
    """
    Komposes video akhir:
      Input 0  : video latar (atau warna solid)
      Input 1  : overlay PNG (RGBA)
      Input 2* : audio (opsional)

    Filter:
      • Scale + crop video latar ke 1080×1920
      • Composite overlay dengan alpha
      • Animasi progress bar via drawbox (lebar = 780 × t/duration px)
    """
    W, H = CANVAS_W, CANVAS_H
    r, g, b = hex_to_rgb(canvas_bg)
    bg_hex = f"0x{r:02x}{g:02x}{b:02x}"

    # Progress bar: x=150, y=1850, h=8, total w=780
    pb_x, pb_y, pb_h = 150, 1850, 8
    pb_w = W - 300  # 780

    # ── Bangun argumen input ──────────────────────────────────────────────
    inputs: list[str] = []
    if bg_video_path:
        inputs += ["-stream_loop", "-1", "-t", str(duration), "-i", str(bg_video_path)]
    else:
        inputs += [
            "-f", "lavfi",
            "-i", f"color=c={bg_hex}:s={W}x{H}:r={fps}:d={duration}",
        ]
    inputs += ["-i", str(overlay_path)]
    overlay_idx = 1

    if audio_path:
        inputs += ["-i", str(audio_path)]
        audio_idx = 2
    else:
        audio_idx = None

    # ── Bangun filter_complex ─────────────────────────────────────────────
    filters: list[str] = []

    # Scale + crop video latar agar persis 1080×1920
    if bg_video_path:
        filters.append(
            f"[0:v]"
            f"scale='if(gt(iw/ih,{W}/{H}),{H}*iw/ih,{W})':"
            f"'if(gt(iw/ih,{W}/{H}),{H},{W}*ih/iw)',"
            f"crop={W}:{H},"
            f"setpts=PTS-STARTPTS[bg]"
        )
    else:
        filters.append("[0:v]setpts=PTS-STARTPTS[bg]")

    # Composite overlay
    filters.append(f"[bg][{overlay_idx}:v]overlay=0:0:format=auto[comp]")

    # Track progress bar (abu transparan)
    filters.append(
        f"[comp]drawbox=x={pb_x}:y={pb_y}:w={pb_w}:h={pb_h}:"
        f"color=0xFFFFFF40:t=fill[comp1]"
    )

    # Batang progress animasi (putih, lebar meningkat seiring waktu)
    filters.append(
        f"[comp1]drawbox=x={pb_x}:y={pb_y}:"
        f"w=min({pb_w}\\,{pb_w}*t/{duration}):h={pb_h}:"
        f"color=white:t=fill[out]"
    )

    filter_str = ";".join(filters)

    # ── Susun perintah FFmpeg ─────────────────────────────────────────────
    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex", filter_str,
        "-map", "[out]",
    ]

    if audio_idx is not None:
        cmd += [
            "-map", f"{audio_idx}:a",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
        ]
    else:
        cmd += ["-an"]

    cmd += [
        "-c:v",     "libx264",
        "-preset",  "fast",
        "-crf",     "23",
        "-pix_fmt", "yuv420p",
        "-t",       str(duration),
        "-r",       str(fps),
        str(output_path),
    ]

    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "Perintah `ffmpeg` tidak ditemukan di PATH. "
            "Pasang dulu (mis. `sudo apt install ffmpeg`)."
        )

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError as e:
        raise RuntimeError(f"Gagal menjalankan ffmpeg: {e}") from e

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg gagal:\n{result.stderr[-2000:]}")


# ─── Endpoint Utama ────────────────────────────────────────────────────────────
@app.post("/generate-video", response_model=VideoResponse, summary="Buat video dari judul dan isi")
async def generate_video(req: VideoRequest):
    """
    ## Alur Proses
    1. **Judul & isi** → diambil langsung dari JSON input
    2. **Gambar** → dari `image_b64` jika disuplai
    3. **Auto Layout** → hitung posisi gambar/judul/ringkasan agar proporsional
       (field posisi bernilai `"auto"` akan dihitung; nilai int akan dihormati)
    4. **PIL** → render overlay PNG (foto, gradient, judul, ringkasan, watermark)
    5. **FFmpeg** → composite overlay + video/warna BG + progress bar animasi + audio
    6. Return **base64 MP4**
    """

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)

        bg_video_path = resolve_bg_video_path(req, tmpdir)
        audio_path = resolve_audio_path(req, tmpdir)

        title = req.judul
        summary = req.isi
        image_bytes = decode_b64(req.image_b64)
        layout = compute_layout(image_bytes, title, summary, req)

        # Render overlay ─────────────────────────────────────────────────────
        overlay_img = render_overlay(image_bytes, title, summary, req, layout)

        # Komposisi video ─────────────────────────────────────────────────────
        overlay_path = tmpdir / "overlay.png"
        overlay_img.save(str(overlay_path), "PNG")

        output_path = tmpdir / "output.mp4"

        # Jalankan ffmpeg di thread agar tidak blokir event loop
        try:
            await asyncio.to_thread(
                compose_video,
                overlay_path,
                bg_video_path,
                audio_path,
                req.canvas_bg_color,
                output_path,
                req.duration,
                FPS,
            )
        except RuntimeError as e:
            raise HTTPException(422, str(e)) from e

        video_b64 = base64.b64encode(output_path.read_bytes()).decode()

    return VideoResponse(
        video_b64=video_b64,
        title=title,
        summary=summary,
        duration=req.duration,
    )


# ─── Health Check ──────────────────────────────────────────────────────────────
@app.get("/", tags=["health"])
def root():
    return {
        "status":          "ok",
        "service":         "News Breaking Video API v1.0",
        "ffmpeg":          shutil.which("ffmpeg") or "NOT INSTALLED",
        "default_bg_video": str(DEFAULT_BG_VIDEO) if DEFAULT_BG_VIDEO.is_file() else None,
        "default_audio":   str(DEFAULT_AUDIO)    if DEFAULT_AUDIO.is_file()    else None,
        "endpoints": {
            "POST /generate-video": "Buat video dari judul dan isi",
            "GET  /docs":           "Swagger UI interaktif",
        },
    }


# ─── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    host = os.getenv("UVICORN_HOST", "0.0.0.0")
    port = int(os.getenv("UVICORN_PORT", "8000"))
    # Auto-reload hanya saat development (UVICORN_RELOAD=1).
    # Di systemd jangan aktifkan reload — pakai `systemctl restart` saja.
    reload = os.getenv("UVICORN_RELOAD", "0") == "1"
    uvicorn.run("main:app", host=host, port=port, reload=reload)
