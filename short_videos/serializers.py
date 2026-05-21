"""
ConnectDial — Serializers (Final)
==================================
Key fixes
─────────
  - VideoCommentCreateSerializer: 'video' field REMOVED — video instance is
    passed directly via serializer.save(video=video) in the view, bypassing
    all UUID / PrimaryKeyRelatedField lookup issues entirely.
  - VideoCommentCreateSerializer: accepts both 'content' and 'body' from the
    frontend (RN sends 'content', model stores 'body').
  - VideoCommentSerializer: exposes both 'content' and 'body' so RN reads work.
  - Removed duplicate MentionedUserSerializer / CommentMentionSerializer classes.
  - VideoShareSerializer / VideoViewSerializer: 'video' also removed and passed
    via save() to avoid the same UUID serializer lookup problem.
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
# COMMENTS — READ
# ─────────────────────────────────────────────────────────────────────────────

# serializers.py
# =============================================================================

class VideoCommentSerializer(serializers.ModelSerializer):
    """
    Read serializer returned to the frontend after GET or POST.
    Exposes both 'body' and 'content' safely without causing duplicate attribute compilation bugs.
    """
    author_details = serializers.SerializerMethodField()
    mentions       = CommentMentionSerializer(many=True, read_only=True)
    reply_count    = serializers.SerializerMethodField()
    content        = serializers.SerializerMethodField() # Changed to a safe Method Field

    class Meta:
        model  = VideoComment
        fields = [
            'id',
            'video',
            'author_details',
            'body',
            'content',      # Safe alias target for React Native frontend
            'mentions',
            'reply_count',
            'created_at',
            'is_edited',
        ]
        read_only_fields = ['id', 'created_at', 'is_edited']

    def get_content(self, obj):
        # Gracefully handle the db_column='text' field extraction proxy
        return obj.body if obj.body else ""

# serializers.py
# =============================================================================

    def get_author_details(self, obj):
        request = self.context.get('request')
        author = obj.author
        
        avatar_url = None
        
        # Check if the author object is empty or anonymous to prevent attribute failures
        if not author or author.is_anonymous:
            return {
                'id': None,
                'username': 'anonymous',
                'display_name': 'Anonymous User',
                'profile_pic': None,
            }

        display_name = author.username
        profile = getattr(author, 'profile', None)
        if not profile:
            profile = getattr(author, 'userprofile', None) or getattr(author, 'user_profile', None)

        if profile:
            display_name = getattr(profile, 'display_name', author.username)
            try:
                if getattr(profile, 'avatar', None):
                    avatar_url = (
                        request.build_absolute_uri(profile.avatar.url)
                        if request else profile.avatar.url
                    )
            except Exception:
                pass

        return {
            'id':           author.id,
            'username':     author.username,
            'display_name': display_name,
            'profile_pic':  avatar_url,
        }

    def get_reply_count(self, obj):
        return obj.replies.count() if hasattr(obj, 'replies') else 0
# ─────────────────────────────────────────────────────────────────────────────
# COMMENTS — WRITE
# ─────────────────────────────────────────────────────────────────────────────

class VideoCommentCreateSerializer(serializers.ModelSerializer):
    """
    Write serializer for creating and updating comments.

    IMPORTANT — 'video' is intentionally NOT in fields.
    The view calls serializer.save(video=video_instance) directly,
    which avoids all UUID / PrimaryKeyRelatedField parsing entirely.

    Accepts BOTH 'content' (what RN sends) and 'body' (model field).
    Maps content → body before saving.
    """
    content = serializers.CharField(required=False, write_only=True)

    class Meta:
        model  = VideoComment
        fields = ['id', 'parent', 'body', 'content']
        read_only_fields = ['id']
        extra_kwargs = {
            'body':   {'required': False},
            'parent': {'required': False, 'allow_null': True},
        }

    def validate(self, attrs):
        # Accept 'content' as alias for 'body'
        if 'content' in attrs and not attrs.get('body'):
            attrs['body'] = attrs.pop('content')
        else:
            attrs.pop('content', None)

        body = attrs.get('body', '') or ''
        if not body.strip():
            raise serializers.ValidationError({'content': 'Comment cannot be empty.'})
        if len(body) > 1000:
            raise serializers.ValidationError({'content': 'Comment is too long (max 1 000 characters).'})
        attrs['body'] = body.strip()
        return attrs

    def validate_parent(self, value):
        if value and value.parent_id is not None:
            raise serializers.ValidationError(
                "Replies to replies are not supported. Use @mention instead."
            )
        return value

    def update(self, instance, validated_data):
        # is_edited is injected by the view via save(is_edited=True)
        is_edited = validated_data.pop('is_edited', None)
        instance  = super().update(instance, validated_data)
        if is_edited is not None:
            instance.is_edited = is_edited
            instance.save(update_fields=['is_edited'])
        return instance


# ─────────────────────────────────────────────────────────────────────────────
# SHORT VIDEO — READ
# ─────────────────────────────────────────────────────────────────────────────

class ShortVideoSerializer(serializers.ModelSerializer):
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
        path    = f"/api/videos/shorts/{obj.pk}/stream/"
        token   = None
        if request and request.auth:
            token = request.auth.key
        if token:
            path = f"{path}?token={token}"
        return request.build_absolute_uri(path) if request else path

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
    video = serializers.FileField(required=False)
    file  = serializers.FileField(required=False, write_only=True)

    class Meta:
        model  = ShortVideo
        fields = ['caption', 'league', 'team', 'video', 'file']

    def validate(self, attrs):
        if 'file' in attrs and not attrs.get('video'):
            attrs['video'] = attrs.pop('file')
        else:
            attrs.pop('file', None)
        return attrs

    def validate_video(self, value):
        if not value:
            return value
        content_type = getattr(value, 'content_type', '') or ''
        if content_type and not content_type.startswith('video/'):
            raise serializers.ValidationError(
                f"Uploaded file must be a video. Received: {content_type}"
            )
        max_size_bytes = 2 * 1024 * 1024 * 1024  # 2 GB
        if value.size > max_size_bytes:
            size_gb = value.size / (1024 * 1024 * 1024)
            raise serializers.ValidationError(
                f"Video file is too large ({size_gb:.2f} GB). Maximum allowed size is 2 GB."
            )
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
    """
    'video' is excluded — passed via serializer.save(video=video_instance).
    """
    class Meta:
        model  = VideoShare
        fields = ['id', 'platform', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_platform(self, value):
        valid = {c[0] for c in VideoShare.PLATFORM_CHOICES}
        if value not in valid:
            raise serializers.ValidationError(
                f"Platform must be one of: {', '.join(sorted(valid))}"
            )
        return value


class VideoViewSerializer(serializers.ModelSerializer):
    """
    'video' is excluded — passed via serializer.save(video=video_instance).
    """
    completed = serializers.BooleanField(read_only=True)

    class Meta:
        model  = VideoView
        fields = ['id', 'watch_time', 'completed', 'created_at']
        read_only_fields = ['id', 'completed', 'created_at']

    def validate_watch_time(self, value):
        if value < 0:
            raise serializers.ValidationError("watch_time cannot be negative.")
        if value > 7200:
            raise serializers.ValidationError("watch_time cannot exceed 7200 seconds (2 hrs).")
        return value