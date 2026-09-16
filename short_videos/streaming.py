"""Streaming and share helpers for SportTribe short videos."""

from urllib.parse import quote

from rest_framework import status
from rest_framework.response import Response

from connectdial.media import storage_object_response


def stream_video_response(request, video_instance):
    """Stream a ShortVideo/FileField through the public API with Range support.

    The MinIO endpoint is private to Docker, so clients must never be redirected
    to ``http://minio:9000``. ``storage_object_response`` reads the object from
    MinIO server-side and preserves native video Range requests (206 responses).
    """
    video_file = getattr(video_instance, 'video', video_instance)

    if not video_file or not getattr(video_file, 'name', None):
        return Response(
            {'detail': 'No video file attached.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    return storage_object_response(request, video_file.name)


def build_whatsapp_share_text(video, share_url: str) -> str:
    lines = [
        "🎬 *[Video]* SportTribe",
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

    lines.append(f"▶️ Watch: {share_url}")
    return "\n".join(lines)


def build_telegram_share_text(video, share_url: str) -> str:
    league_team = " | ".join(filter(None, [
        video.league.name if video.league else None,
        video.team.name if video.team else None,
    ]))

    caption = (video.caption[:100] + "…") if len(video.caption) > 100 else video.caption

    text = (
        f"🎬 <b>[Video]</b> SportTribe\n"
        f"👤 <b>@{video.author.username}</b>\n"
    )
    if league_team:
        text += f"🏆 {league_team}\n"
    if caption:
        text += f"📝 {caption}\n"
    text += f'▶️ <a href="{share_url}">Watch on SportTribe</a>'
    return text
