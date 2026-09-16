# short_videos/models.py

import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def short_video_upload_path(instance, filename):
    ext = filename.rsplit('.', 1)[-1].lower()
    return f"shorts/{instance.pk}/{uuid.uuid4().hex}.{ext}"


# ─────────────────────────────────────────────────────────────
# SHORT VIDEO
# ─────────────────────────────────────────────────────────────

class ShortVideo(models.Model):

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('processing', 'Processing'),
        ('published', 'Published'),
        ('failed', 'Failed'),
        ('rejected', 'Rejected'),
        ('banned', 'Banned'),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='short_videos',
    )

    video = models.FileField(
        upload_to=short_video_upload_path
    )

    thumbnail = models.ImageField(
        upload_to='shorts/thumbnails/',
        blank=True,
        null=True
    )

    caption = models.TextField(
        blank=True,
        max_length=2200
    )

    league = models.ForeignKey(
        'leagues.League',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='short_videos',
    )

    team = models.ForeignKey(
        'leagues.Team',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='short_videos',
    )

    duration = models.PositiveIntegerField(
        default=0,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(7200),
        ],
    )

    width = models.PositiveIntegerField(
        null=True,
        blank=True
    )

    height = models.PositiveIntegerField(
        null=True,
        blank=True
    )

    file_size = models.PositiveBigIntegerField(
        null=True,
        blank=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='published'
    )

    cached_likes = models.PositiveIntegerField(
        default=0,
        db_index=True
    )

    cached_comments = models.PositiveIntegerField(default=0)
    cached_shares = models.PositiveIntegerField(default=0)
    cached_views = models.PositiveIntegerField(default=0)

    cached_avg_watch_ratio = models.FloatField(default=0.0)

    created_at = models.DateTimeField(
        default=timezone.now,
        db_index=True
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

        indexes = [
            models.Index(fields=['league', '-created_at']),
            models.Index(fields=['team', '-created_at']),
            models.Index(fields=['author', '-created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['cached_likes']),
        ]

    def __str__(self):
        return f"ShortVideo({self.id})"

    @property
    def duration_display(self):
        s = self.duration
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)

        if h:
            return f"{h}:{m:02d}:{sec:02d}"

        return f"{m}:{sec:02d}"


# ─────────────────────────────────────────────────────────────
# VIDEO LIKE
# ─────────────────────────────────────────────────────────────

class VideoLike(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='video_likes',
    )

    video = models.ForeignKey(
        ShortVideo,
        on_delete=models.CASCADE,
        related_name='likes'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'video')


# ─────────────────────────────────────────────────────────────
# VIDEO COMMENT
# ─────────────────────────────────────────────────────────────

class VideoComment(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    video = models.ForeignKey(
        ShortVideo,
        on_delete=models.CASCADE,
        related_name='comments',
        db_index=True
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='video_comments',
    )

    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='replies'
    )

    content = models.TextField(max_length=1000)

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )

    updated_at = models.DateTimeField(auto_now=True)

    is_edited = models.BooleanField(default=False)

    # Cached counter updated by VideoCommentLikeToggleView — avoids COUNT queries
    cached_likes = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['created_at']

        indexes = [
            models.Index(
                fields=['video', 'parent', 'created_at']
            ),
        ]

    def __str__(self):
        return f"Comment {self.id}"


# ─────────────────────────────────────────────────────────────
# COMMENT MENTIONS
# ─────────────────────────────────────────────────────────────

class CommentMention(models.Model):

    comment = models.ForeignKey(
        VideoComment,
        on_delete=models.CASCADE,
        related_name='mentions'
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='mentioned_in_comments',
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('comment', 'user')


# ─────────────────────────────────────────────────────────────
# VIDEO COMMENT LIKE
# ─────────────────────────────────────────────────────────────

class VideoCommentLike(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='comment_likes',
    )

    comment = models.ForeignKey(
        VideoComment,
        on_delete=models.CASCADE,
        related_name='likes',
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'comment')


# ─────────────────────────────────────────────────────────────
# VIDEO SHARE
# ─────────────────────────────────────────────────────────────

class VideoShare(models.Model):

    PLATFORM_CHOICES = [
        ('whatsapp', 'WhatsApp'),
        ('telegram', 'Telegram'),
        ('twitter', 'Twitter / X'),
        ('facebook', 'Facebook'),
        ('instagram', 'Instagram'),
        ('copy_link', 'Copy Link'),
        ('reshare', 'In-App Reshare'),
        ('other', 'Other'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='video_shares',
    )

    video = models.ForeignKey(
        ShortVideo,
        on_delete=models.CASCADE,
        related_name='shares'
    )

    platform = models.CharField(
        max_length=20,
        choices=PLATFORM_CHOICES,
        default='other'
    )

    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────
# VIDEO VIEW
# ─────────────────────────────────────────────────────────────

class VideoView(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='video_views',
    )

    video = models.ForeignKey(
        ShortVideo,
        on_delete=models.CASCADE,
        related_name='views'
    )

    watch_time = models.FloatField(default=0.0)

    completed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['video', 'created_at']),
            models.Index(fields=['user', 'created_at']),
        ]

    def save(self, *args, **kwargs):

        duration = self.video.duration if self.video_id else 0

        if duration > 0:
            self.completed = self.watch_time >= (duration * 0.9)
        else:
            self.completed = False

        super().save(*args, **kwargs)