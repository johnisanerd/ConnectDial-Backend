"""
ConnectDial — Signals
=====================
Responsibilities:
  1. Keep cached_* counters on ShortVideo in sync.
  2. Maintain cached_avg_watch_ratio for better feed performance.
  3. Parse @mentions and create CommentMention rows.
  4. Notify mentioned users.
  5. Bust feed cache on new video uploads.
"""

import re
from django.db import models, transaction
from django.db.models import Avg, F
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings

from .models import (
    VideoLike, VideoComment, CommentMention,
    VideoShare, VideoView, ShortVideo,
)


def _get_user_model():
    from django.contrib.auth import get_user_model
    return get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# HELPER: Counter Update
# ─────────────────────────────────────────────────────────────────────────────

def _update_cached(video_id, field: str, delta: int) -> None:
    """Atomic F() counter update with floor at 0."""
    ShortVideo.objects.filter(pk=video_id).update(
        **{field: models.Case(
            models.When(
                **{f'{field}__gt': 0},
                then=models.F(field) + delta,
            ),
            default=models.Value(0),
            output_field=models.PositiveIntegerField(),
        ) if delta < 0 else models.F(field) + delta}
    )


def _update_avg_watch_ratio(video_id):
    """Update cached_avg_watch_ratio after a new view is recorded."""
    from django.db.models import Avg, F, FloatField
    from django.db.models.functions import Coalesce

    avg = VideoView.objects.filter(video_id=video_id).aggregate(
        avg_watch=Coalesce(Avg('watch_time'), 0.0, output_field=FloatField())
    )['avg_watch']

    ShortVideo.objects.filter(pk=video_id).update(
        cached_avg_watch_ratio=avg
    )


# ─────────────────────────────────────────────────────────────────────────────
# LIKES
# ─────────────────────────────────────────────────────────────────────────────

@receiver(post_save, sender=VideoLike)
def like_created(sender, instance, created, **kwargs):
    if created:
        _update_cached(instance.video_id, 'cached_likes', 1)


@receiver(post_delete, sender=VideoLike)
def like_deleted(sender, instance, **kwargs):
    _update_cached(instance.video_id, 'cached_likes', -1)


# ─────────────────────────────────────────────────────────────────────────────
# COMMENTS + MENTIONS
# ─────────────────────────────────────────────────────────────────────────────

_MENTION_RE = re.compile(r'@([\w.]+)')


def _resolve_mentions(content: str):
    User = _get_user_model()
    handles = set(_MENTION_RE.findall(content))
    if not handles:
        return []
    return list(User.objects.filter(username__in=handles))


def _create_mention_rows(comment: VideoComment, users: list) -> None:
    CommentMention.objects.bulk_create(
        [CommentMention(comment=comment, user=u) for u in users],
        ignore_conflicts=True,
    )


def _notify_mentioned_users(comment: VideoComment, users: list) -> None:
    """TODO: Connect to your notification service (FCM, In-app, etc.)"""
    pass


@receiver(post_save, sender=VideoComment)
def comment_saved(sender, instance, created, **kwargs):
    if created:
        _update_cached(instance.video_id, 'cached_comments', 1)

    mentioned = _resolve_mentions(instance.content)

    if mentioned:
        if not created:
            with transaction.atomic():
                CommentMention.objects.filter(comment=instance).delete()
                _create_mention_rows(instance, mentioned)
        else:
            _create_mention_rows(instance, mentioned)
            _notify_mentioned_users(instance, mentioned)
    elif not created:
        CommentMention.objects.filter(comment=instance).delete()


@receiver(post_delete, sender=VideoComment)
def comment_deleted(sender, instance, **kwargs):
    _update_cached(instance.video_id, 'cached_comments', -1)


# ─────────────────────────────────────────────────────────────────────────────
# SHARES
# ─────────────────────────────────────────────────────────────────────────────

@receiver(post_save, sender=VideoShare)
def share_created(sender, instance, created, **kwargs):
    if created:
        _update_cached(instance.video_id, 'cached_shares', 1)


@receiver(post_delete, sender=VideoShare)
def share_deleted(sender, instance, **kwargs):
    _update_cached(instance.video_id, 'cached_shares', -1)


# ─────────────────────────────────────────────────────────────────────────────
# VIEWS (Important: Also updates watch ratio)
# ─────────────────────────────────────────────────────────────────────────────

@receiver(post_save, sender=VideoView)
def view_created(sender, instance, created, **kwargs):
    if created:
        _update_cached(instance.video_id, 'cached_views', 1)
        _update_avg_watch_ratio(instance.video_id)   # New


@receiver(post_delete, sender=VideoView)
def view_deleted(sender, instance, **kwargs):
    _update_cached(instance.video_id, 'cached_views', -1)
    _update_avg_watch_ratio(instance.video_id)       # New


# ─────────────────────────────────────────────────────────────────────────────
# NEW VIDEO → Cache Busting
# ─────────────────────────────────────────────────────────────────────────────

@receiver(post_save, sender=ShortVideo)
def video_published(sender, instance, created, **kwargs):
    if not created:
        return

    from .feed_algorithm import bust_feed_cache

    bust_feed_cache(instance.author_id)

    try:
        follower_ids = instance.author.followers.values_list('follower_id', flat=True)
        for uid in follower_ids:
            bust_feed_cache(uid)
    except AttributeError:
        # Follow model not set up yet
        pass