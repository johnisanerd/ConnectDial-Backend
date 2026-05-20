"""
ConnectDial — Video Processing Utilities
"""

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
        )
        return int(float(result.stdout.strip()))
    except Exception:
        return 0


def compress_video(input_path: str, output_path: str) -> None:
    """Re-encode with faststart for progressive playback."""
    subprocess.run(
        [
            'ffmpeg', '-i', input_path,
            '-vcodec', 'libx264',
            '-crf', '28',
            '-preset', 'fast',
            '-acodec', 'aac',
            '-b:a', '128k',
            '-movflags', '+faststart',
            '-y',
            output_path,
        ],
        check=True,
        timeout=7200,
    )


def generate_thumbnail(video_path: str) -> bytes:
    """Generate JPEG thumbnail at 1-second mark."""
    thumb_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as thumb:
            thumb_path = thumb.name

        subprocess.run(
            [
                'ffmpeg', '-i', video_path,
                '-ss', '00:00:01',
                '-vframes', '1',
                '-vf', 'scale=480:-1',
                '-y', thumb_path,
            ],
            check=True,
            timeout=60,
        )

        with open(thumb_path, 'rb') as f:
            return f.read()
    finally:
        if thumb_path and os.path.exists(thumb_path):
            os.unlink(thumb_path)