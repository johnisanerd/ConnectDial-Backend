"""
ConnectDial — Serializers
==========================

Fixes applied
─────────────
  FIX-1  Added ShortVideoCreateSerializer — a dedicated write serializer for
         ShortVideoUploadView.
"""

import re
from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import (
    ShortVideo, VideoComment, CommentMention,
    VideoLike, VideoShare, VideoView,
)

User = get_user_model()

_MENTION_RE = re.compile(r'@([\w.]+)')


# ─────────────────────────────────────────────────────────────────────────────
# USER (LIGHTWEIGHT)
# ─────────────────────────────────────────────────────────────────────────────

class MentionedUserSerializer(serializers.ModelSerializer):
    class Meta:
        model  = User
        fields = ['id', 'username']


# ─────────────────────────────────────────────────────────────────────────────
# MENTIONS
# ─────────────────────────────────────────────────────────────────────────────

class CommentMentionSerializer(serializers.ModelSerializer):
    user = MentionedUserSerializer(read_only=True)

    class Meta:
        model  = CommentMention
        fields = ['user']


# ─────────────────────────────────────────────────────────────────────────────
# COMMENTS
# ─────────────────────────────────────────────────────────────────────────────

class VideoCommentSerializer(serializers.ModelSerializer):
    """Read serializer for a comment."""
    author_username = serializers.CharField(source='author.username', read_only=True)
    author_avatar   = serializers.SerializerMethodField()
    mentions        = CommentMentionSerializer(many=True, read_only=True)
    reply_count     = serializers.SerializerMethodField()

    class Meta:
        model  = VideoComment
        fields = [
            'id',
            'video',
            'author_username',
            'author_avatar',
            'parent',
            'body',
            'mentions',
            'reply_count',
            'created_at',
            'is_edited',
        ]
        read_only_fields = ['id', 'created_at', 'is_edited']

    def get_author_avatar(self, obj):
        request = self.context.get('request')
        try:
            if obj.author.profile.avatar:
                url = obj.author.profile.avatar.url
                return request.build_absolute_uri(url) if request else url
        except Exception:
            pass
        return None

    def get_reply_count(self, obj):
        return obj.replies.count()


class VideoCommentCreateSerializer(serializers.ModelSerializer):
    """Write serializer for creating / updating a comment."""

    class Meta:
        model  = VideoComment
        fields = ['id', 'video', 'parent', 'body']
        read_only_fields = ['id']

    def validate_body(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Comment body cannot be empty.")
        if len(value) > 1000:
            raise serializers.ValidationError("Comment is too long (max 1000 characters).")
        return value.strip()

    def validate_parent(self, value):
        if value and value.parent_id is not None:
            raise serializers.ValidationError(
                "Replies to replies are not supported. "
                "Tag the user with @mention instead."
            )
        return value

    def create(self, validated_data):
        comment = super().create(validated_data)
        # Mark as edited will be handled in signals for updates
        return comment


# ─────────────────────────────────────────────────────────────────────────────
# SHORT VIDEO — READ
# ─────────────────────────────────────────────────────────────────────────────

class ShortVideoSerializer(serializers.ModelSerializer):
    """
    Read serializer for ShortVideo — used for feed responses and the upload
    response payload.
    """
    author_username  = serializers.CharField(source='author.username', read_only=True)
    author_avatar    = serializers.SerializerMethodField()
    author_id        = serializers.IntegerField(source='author.id', read_only=True)

    league_name      = serializers.CharField(source='league.name', read_only=True, default=None)
    team_name        = serializers.CharField(source='team.name',   read_only=True, default=None)

    likes_count      = serializers.IntegerField(source='cached_likes',    read_only=True)
    comments_count   = serializers.IntegerField(source='cached_comments', read_only=True)
    shares_count     = serializers.IntegerField(source='cached_shares',   read_only=True)
    views_count      = serializers.IntegerField(source='cached_views',    read_only=True)

    duration_display = serializers.CharField(read_only=True)

    video_url        = serializers.SerializerMethodField()
    thumbnail_url    = serializers.SerializerMethodField()
    share_url        = serializers.SerializerMethodField()
    is_liked         = serializers.SerializerMethodField()
    og_title         = serializers.SerializerMethodField()
    og_description   = serializers.SerializerMethodField()

    class Meta:
        model  = ShortVideo
        fields = [
            'id',
            'author_id',
            'author_username',
            'author_avatar',
            'video_url',
            'thumbnail_url',
            'caption',
            'league_name',
            'team_name',
            'duration',
            'duration_display',
            'likes_count',
            'comments_count',
            'shares_count',
            'views_count',
            'is_liked',
            'share_url',
            'og_title',
            'og_description',
            'created_at',
            'status',
        ]

    def get_author_avatar(self, obj):
        request = self.context.get('request')
        try:
            if obj.author.profile.avatar:
                url = obj.author.profile.avatar.url
                return request.build_absolute_uri(url) if request else url
        except Exception:
            pass
        return None

    def get_video_url(self, obj):
        request = self.context.get('request')
        path = f"/api/videos/shorts/{obj.pk}/stream/"

        token = None
        if request and request.auth:
            token = request.auth.key

        if token:
            path = f"{path}?token={token}"

        if request:
            return request.build_absolute_uri(path)
        return path

    def get_thumbnail_url(self, obj):
        request = self.context.get('request')
        if obj.thumbnail:
            url = obj.thumbnail.url
            return request.build_absolute_uri(url) if request else url
        return None

    def get_share_url(self, obj):
        return obj.share_url

    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            # Relies on prefetch_related('likes') from feed
            return obj.likes.filter(user=request.user).exists()
        return False

    def get_og_title(self, obj):
        try:
            return obj.og_title
        except AttributeError:
            return f"{obj.author.username}: {obj.caption[:80]}" if obj.caption else str(obj.id)

    def get_og_description(self, obj):
        try:
            return obj.og_description
        except AttributeError:
            return obj.caption[:200] if obj.caption else ""


# ─────────────────────────────────────────────────────────────────────────────
# SHORT VIDEO — WRITE
# ─────────────────────────────────────────────────────────────────────────────

class ShortVideoCreateSerializer(serializers.ModelSerializer):
    """
    Write serializer for ShortVideoUploadView.

    FIX-1: video field is writable so compressed file goes through proper validation.
    FIX-3: also accept 'file' as the upload field name (what the React Native frontend sends).
    """
    video = serializers.FileField(required=False)
    # Accept 'file' as an alias — the RN frontend appends the video as 'file'
    file  = serializers.FileField(required=False, write_only=True)

    class Meta:
        model  = ShortVideo
        fields = ['caption', 'league', 'team', 'video', 'file']

    def validate(self, attrs):
        # If frontend sent 'file', treat it as 'video'
        if 'file' in attrs and not attrs.get('video'):
            attrs['video'] = attrs.pop('file')
        else:
            attrs.pop('file', None)
        return attrs

    def validate_video(self, value):
        if not value:
            return value

        content_type = getattr(value, 'content_type', '') or ''

        # 1. Must be a video
        if content_type and not content_type.startswith('video/'):
            raise serializers.ValidationError(
                f"Uploaded file must be a video. Received: {content_type}"
            )

        # 2. Enforce 2GB maximum size
        max_size_bytes = 2 * 1024 * 1024 * 1024  # 2GB
        if value.size > max_size_bytes:
            size_gb = value.size / (1024 * 1024 * 1024)
            raise serializers.ValidationError(
                f"Video file is too large ({size_gb:.2f} GB). Maximum allowed size is 2 GB."
            )

        # 3. Optional: Soft warning for large files (can be logged)
        if value.size > 500 * 1024 * 1024:   # > 500MB
            # You can add logging here if desired
            pass

        return value
# ─────────────────────────────────────────────────────────────────────────────
# ENGAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

class VideoLikeSerializer(serializers.ModelSerializer):
    class Meta:
        model  = VideoLike
        fields = ['id', 'video', 'created_at']
        read_only_fields = ['id', 'created_at']


class VideoShareSerializer(serializers.ModelSerializer):
    class Meta:
        model  = VideoShare
        fields = ['id', 'video', 'platform', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_platform(self, value):
        valid = {c[0] for c in VideoShare.PLATFORM_CHOICES}
        if value not in valid:
            raise serializers.ValidationError(
                f"Platform must be one of: {', '.join(sorted(valid))}"
            )
        return value


class VideoViewSerializer(serializers.ModelSerializer):
    completed = serializers.BooleanField(read_only=True)

    class Meta:
        model  = VideoView
        fields = ['id', 'video', 'watch_time', 'completed', 'created_at']
        read_only_fields = ['id', 'completed', 'created_at']

    def validate_watch_time(self, value):
        if value < 0:
            raise serializers.ValidationError("watch_time cannot be negative.")
        if value > 7200:
            raise serializers.ValidationError("watch_time cannot exceed 7200 seconds (2 hrs).")
        return value