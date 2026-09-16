"""SportTribe video processing utilities."""

import os
import subprocess
import tempfile


def extract_duration(file_path: str) -> int:
    """Use ffprobe to read video duration."""
    try:
        result = subprocess.run(
            [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        return max(0, int(float(result.stdout.strip())))
    except Exception:
        return 0


def compress_video(input_path: str, output_path: str) -> None:
    """Create a broadly compatible MP4 optimized for progressive mobile playback."""
    subprocess.run(
        [
            'ffmpeg',
            '-hide_banner',
            '-loglevel', 'error',
            '-i', input_path,
            '-map', '0:v:0',
            '-map', '0:a:0?',
            '-vf', r'scale=min(1080\,iw):-2',
            '-c:v', 'libx264',
            '-preset', 'veryfast',
            '-crf', '26',
            '-pix_fmt', 'yuv420p',
            '-profile:v', 'main',
            '-level', '4.0',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-ar', '48000',
            '-ac', '2',
            '-movflags', '+faststart',
            '-map_metadata', '-1',
            '-y',
            output_path,
        ],
        check=True,
        timeout=7200,
    )


def generate_thumbnail(video_path: str) -> bytes:
    """Generate a JPEG thumbnail near the beginning of the video."""
    thumb_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as thumb:
            thumb_path = thumb.name

        subprocess.run(
            [
                'ffmpeg',
                '-hide_banner',
                '-loglevel', 'error',
                '-ss', '00:00:00.500',
                '-i', video_path,
                '-frames:v', '1',
                '-vf', r'scale=min(720\,iw):-2',
                '-q:v', '3',
                '-y',
                thumb_path,
            ],
            check=True,
            timeout=60,
        )

        with open(thumb_path, 'rb') as f:
            return f.read()
    finally:
        if thumb_path and os.path.exists(thumb_path):
            os.unlink(thumb_path)
