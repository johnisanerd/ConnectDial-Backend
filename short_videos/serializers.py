"""
ConnectDial — Serializers
==========================

Fixes applied
─────────────
  FIX-1  ShortVideoCreateSerializer — dedicated write serializer for
         ShortVideoUploadView.
  FIX-E  VideoCommentCreateSerializer.update() accepts is_edited kwarg
         passed by CommentDetailView.patch().
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
# COMMENTS - Improved to match Post/Comment style
# ─────────────────────────────────────────────────────────────────────────────

class MentionedUserSerializer(serializers.ModelSerializer):
    class Meta:
        model  = User
        fields = ['id', 'username']


class CommentMentionSerializer(serializers.ModelSerializer):
    user = MentionedUserSerializer(read_only=True)

    class Meta:
        model  = CommentMention
        fields = ['user']


class VideoCommentSerializer(serializers.ModelSerializer):
    """Read serializer - consistent with Post Comment style"""
    author_details = serializers.SerializerMethodField()
    mentions       = CommentMentionSerializer(many=True, read_only=True)
    reply_count    = serializers.SerializerMethodField()
    # FIX: expose 'content' alias for 'body' so RN frontend c.content works
    content        = serializers.CharField(source='body', read_only=True)

    class Meta:
        model  = VideoComment
        fields = [
            'id',
            'video',
            'author_details',
            'body',
            'content',
            'mentions',
            'reply_count',
            'created_at',
            'is_edited',
        ]
        read_only_fields = ['id', 'created_at', 'is_edited']

    def get_author_details(self, obj):
        """Consistent author object like in PostSerializer"""
        request = self.context.get('request')
        profile = getattr(obj.author, 'profile', None)

        avatar_url = None
        try:
            if profile and profile.avatar:
                avatar_url = request.build_absolute_uri(profile.avatar.url) if request else profile.avatar.url
        except Exception:
            pass

        return {
            'id':           obj.author.id,
            'username':     obj.author.username,
            'display_name': getattr(profile, 'display_name', obj.author.username),
            'profile_pic':  avatar_url,
            'is_following': False,  # Can be enhanced later with annotation
        }

    def get_reply_count(self, obj):
        return obj.replies.count() if hasattr(obj, 'replies') else 0


class VideoCommentCreateSerializer(serializers.ModelSerializer):
    """
    Write serializer for creating / updating comments.

    FIX: The React Native frontend sends { content: "..." } but the model
    field is `body`. We accept both by mapping `content` → `body` in
    validate() so no model migration is required.
    """
    # Accept 'content' from the frontend as a write-only alias for 'body'
    content = serializers.CharField(required=False, write_only=True)

    class Meta:
        model  = VideoComment
        fields = ['id', 'video', 'parent', 'body', 'content']
        read_only_fields = ['id']
        extra_kwargs = {
            'body': {'required': False},  # not required; content may be used instead
        }

    def validate(self, attrs):
        # Map 'content' → 'body' if frontend sent content instead of body
        if 'content' in attrs and not attrs.get('body'):
            attrs['body'] = attrs.pop('content')
        else:
            attrs.pop('content', None)

        body = attrs.get('body', '')
        if not body or not body.strip():
            raise serializers.ValidationError({'content': 'Comment cannot be empty.'})
        if len(body) > 1000:
            raise serializers.ValidationError({'content': 'Comment is too long (max 1000 characters).'})
        attrs['body'] = body.strip()
        return attrs

    def validate_parent(self, value):
        if value and value.parent_id is not None:
            raise serializers.ValidationError(
                "Replies to replies are not supported. Use @mention instead."
            )
        return value

    def create(self, validated_data):
        return super().create(validated_data)

    def update(self, instance, validated_data):
        is_edited = validated_data.pop('is_edited', None)
        instance = super().update(instance, validated_data)
        if is_edited is not None:
            instance.is_edited = is_edited
            instance.save(update_fields=['is_edited'])
        return instance
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
        """
        Returns the streaming URL: /api/videos/shorts/<pk>/stream/?token=<tok>
        The token is appended so react-native-video can authenticate the range
        request without sending Authorization headers (not supported by all
        video players).
        """
        request = self.context.get('request')
        path    = f"/api/videos/shorts/{obj.pk}/stream/"

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
        return obj.share_url  # https://connectdial.com/shorts/<pk>/

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
    """
    Write serializer for ShortVideoUploadView.

    FIX-1: video field is writable so the compressed file goes through proper
           validation.
    FIX-3: also accept 'file' as the upload field name (what the RN frontend
           sends via FormData).
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
            raise serializers.ValidationError(
                "watch_time cannot exceed 7200 seconds (2 hrs)."
            )
        return value