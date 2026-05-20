"""
Streaming utilities for ConnectDial short videos.
"""

import os
import mimetypes
from urllib.parse import urlparse

from django.http import StreamingHttpResponse, HttpResponseRedirect
from django.conf import settings


CHUNK_SIZE = 1024 * 512  # 512 KB


def _is_external_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ('http', 'https') and bool(parsed.netloc)


def stream_video_response(request, video_instance):
    video_file = video_instance.video

    if not video_file or not video_file.name:
        from rest_framework.response import Response
        from rest_framework import status
        return Response(
            {'detail': 'No video file attached.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    file_url = video_file.url

    # External storage (S3, GCS, CDN, etc.)
    if _is_external_url(file_url):
        return HttpResponseRedirect(file_url)

    # Local development serving
    media_root = getattr(settings, 'MEDIA_ROOT', '')
    if not media_root:
        from rest_framework.response import Response
        from rest_framework import status
        return Response(
            {'detail': 'MEDIA_ROOT is not configured.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    file_path = os.path.join(media_root, video_file.name)

    if not os.path.exists(file_path):
        from rest_framework.response import Response
        from rest_framework import status
        return Response(
            {'detail': 'Video file not found on disk.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    file_size = os.path.getsize(file_path)
    content_type, _ = mimetypes.guess_type(file_path)
    content_type = content_type or 'video/mp4'

    range_header = request.META.get('HTTP_RANGE', '').strip()

    if range_header:
        byte_range = range_header.replace('bytes=', '')
        start_str, _, end_str = byte_range.partition('-')
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else file_size - 1
        end = min(end, file_size - 1)
        length = end - start + 1

        def file_iterator(path, offset, read_len, chunk=CHUNK_SIZE):
            with open(path, 'rb') as f:
                f.seek(offset)
                remaining = read_len
                while remaining > 0:
                    data = f.read(min(chunk, remaining))
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        response = StreamingHttpResponse(
            file_iterator(file_path, start, length),
            status=206,
            content_type=content_type,
        )
        response['Content-Length'] = str(length)
        response['Content-Range'] = f'bytes {start}-{end}/{file_size}'
        response['Accept-Ranges'] = 'bytes'
        response['Cache-Control'] = 'public, max-age=86400'
        return response

    # Full file
    def full_iterator(path, chunk=CHUNK_SIZE):
        with open(path, 'rb') as f:
            while True:
                data = f.read(chunk)
                if not data:
                    break
                yield data

    response = StreamingHttpResponse(full_iterator(file_path), content_type=content_type)
    response['Content-Length'] = str(file_size)
    response['Accept-Ranges'] = 'bytes'
    response['Cache-Control'] = 'public, max-age=86400'
    return response


def build_whatsapp_share_text(video) -> str:
    lines = [
        "🎬 *[Video]* ConnectDial",
        f"👤 @{video.author.username}",
    ]
    if video.league or video.team:
        ctx = " • ".join(filter(None, [
            video.league.name if video.league else None,
            video.team.name if video.team else None,
        ]))
        lines.append(f"🏆 {ctx}")

    if video.caption:
        caption = (video.caption[:120] + "…") if len(video.caption) > 120 else video.caption
        lines.append(f"📝 {caption}")

    lines.append(f"▶️ Watch: {video.share_url}")
    return "\n".join(lines)


def build_telegram_share_text(video) -> str:
    league_team = " | ".join(filter(None, [
        video.league.name if video.league else None,
        video.team.name if video.team else None,
    ]))

    caption = (video.caption[:100] + "…") if len(video.caption) > 100 else video.caption

    text = (
        f"🎬 <b>[Video]</b> ConnectDial\n"
        f"👤 <b>@{video.author.username}</b>\n"
    )
    if league_team:
        text += f"🏆 {league_team}\n"
    if caption:
        text += f"📝 {caption}\n"
    text += f'▶️ <a href="{video.share_url}">Watch on ConnectDial</a>'
    return text