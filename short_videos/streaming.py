"""Streaming and share helpers for SportTribe short videos."""

from django.http import HttpResponseRedirect
from rest_framework import status
from rest_framework.response import Response

from connectdial.media import build_media_url


def stream_video_response(request, video_instance):
    """Legacy stream endpoint that redirects to Firebase/GCS.

    Current serializers return the signed storage URL directly so native video
    players can use Google Cloud Storage byte-range support without Django in
    the media data path. This endpoint remains for older application builds.
    """
    video_file = getattr(video_instance, 'video', video_instance)

    if not video_file or not getattr(video_file, 'name', None):
        return Response(
            {'detail': 'No video file attached.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    url = build_media_url(video_file, request)
    if not url:
        return Response(
            {'detail': 'Video file is unavailable.'},
            status=status.HTTP_404_NOT_FOUND,
        )
    return HttpResponseRedirect(url)


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
    text += f'<a href="{share_url}">▶️ Watch on SportTribe</a>'
    return text
