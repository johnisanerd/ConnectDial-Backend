"""
ConnectDial — Short Video Serializers (Optimized Baseline)
=============================================================================
Design updates applied following the Posts app architecture pattern:
  - Added SupportLogicMixin to dynamically inject "Supports [Team]" contextual badges.
  - Implemented a unified _author_dict helper to prevent double model relation evaluations.
  - Explicitly declared 'video' and 'file' as writable fields on ShortVideoCreateSerializer 
    to guarantee multi-part parser streams aren't silently discarded by DRF filters.
  - Keeps VideoCommentSerializer as a lightweight, secure read-only container.
"""

import re
from rest_framework import serializers
from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes

from .models import (
    ShortVideo, VideoComment, CommentMention,
    VideoLike, VideoShare, VideoView
)

User = get_user_model()
_MENTION_RE = re.compile(r'@([\w.]+)')


# ─────────────────────────────────────────────────────────────────────────────
# REUSABLE PIPELINE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _build_url(request, file_field):
    """Return an absolute URL path signature for a FileField or ImageField, or None."""
    if not file_field:
        return None
    try:
        url = file_field.url
    except Exception:
        return None
    return request.build_absolute_uri(url) if request else url


def _author_dict(user, request):
    """
    Build unified, lightweight author profiles.
    Guarantees performance gains by reading items already allocated to memory.
    """
    if not user or user.is_anonymous:
        return {
            'id':           None,
            'username':     'Anonymous',
            'display_name': 'Anonymous User',
            'profile_pic':  None,
            'account_type': 'fan',
        }

    profile = getattr(user, 'user_profile', None)
    if not profile:
        profile = getattr(user, 'userprofile', None) or getattr(user, 'user_profile', None)
        
    profile_pic = _build_url(request, getattr(profile, 'avatar', getattr(profile, 'profile_image', None)))

    return {
        'id':           user.id,
        'username':     user.username,
        'display_name': (profile.display_name if profile and getattr(profile, 'display_name', None) else user.username),
        'profile_pic':  profile_pic,
        'account_type': getattr(user, 'account_type', 'fan'),
        'badge_type':   getattr(user, 'badge_type', None),
    }


# ─────────────────────────────────────────────────────────────────────────────
# SUPPORT CONTEXT MIXIN
# ─────────────────────────────────────────────────────────────────────────────

class SupportLogicMixin:
    """
    Resolves the active team badge tracking next to videos or commentary records.
    """
    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_supporting_info(self, obj):
        user = getattr(obj, 'author', getattr(obj, 'user', None))
        if not user or user.is_anonymous:
            return None

        if getattr(user, 'account_type', None) in ('news', 'organization'):
            return None

        target_league = getattr(obj, 'league', None)
        if not target_league and hasattr(obj, 'video'):
            target_league = getattr(obj.video, 'league', None)

        if target_league:
            pref = next(
                (p for p in user.fan_preferences.all() if p.league_id == target_league.id),
                None,
            ) if hasattr(user, 'fan_preferences') else None
            
            if pref and pref.team:
                return {
                    'team_name':   pref.team.name,
                    'team_logo':   _build_url(None, pref.team.logo),
                    'league_name': target_league.name,
                    'type':        'contextual',
                }

        fav_team   = getattr(user, 'favorite_team', None)
        fav_league = getattr(user, 'favorite_league', None)
        if fav_team:
            return {
                'team_name':   fav_team.name,
                'team_logo':   _build_url(None, fav_team.logo),
                'league_name': fav_league.name if fav_league else 'Global',
                'type':        'global',
            }

        return None


# ─────────────────────────────────────────────────────────────────────────────
# MENTIONS
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


# ─────────────────────────────────────────────────────────────────────────────
# COMMENTS
# ─────────────────────────────────────────────────────────────────────────────

class VideoCommentSerializer(SupportLogicMixin, serializers.Serializer):
    """
    Read-only comment structure decoupled from heavy relational model properties.
    """
    id              = serializers.UUIDField(read_only=True)
    video_id        = serializers.UUIDField(read_only=True)
    content = serializers.CharField(read_only=True)
    author_details  = serializers.SerializerMethodField()
    supporting_info = serializers.SerializerMethodField()
    reply_count     = serializers.SerializerMethodField()
    created_at      = serializers.DateTimeField(read_only=True)
    is_edited       = serializers.BooleanField(read_only=True)



    @extend_schema_field(OpenApiTypes.INT)
    def get_reply_count(self, obj):
        return obj.replies.count() if hasattr(obj, 'replies') else 0

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_author_details(self, obj):
        request = self.context.get('request')
        return _author_dict(obj.author, request)


class VideoCommentCreateSerializer(serializers.ModelSerializer):

    class Meta:
        model = VideoComment
        fields = ['id', 'parent', 'content']
        read_only_fields = ['id']

        extra_kwargs = {
            'parent': {
                'required': False,
                'allow_null': True,
            },
            'content': {
                'required': True,
            }
        }

    def validate_content(self, value):
        value = (value or '').strip()

        if not value:
            raise serializers.ValidationError("Comment cannot be empty.")

        if len(value) > 1000:
            raise serializers.ValidationError(
                "Comment is too long (max 1000 characters)."
            )

        return value

    def validate_parent(self, value):
        if value and value.parent_id is not None:
            raise serializers.ValidationError(
                "Nested sub-replies are disabled."
            )
        return value
# ─────────────────────────────────────────────────────────────────────────────
# SHORT VIDEO — READ
# ─────────────────────────────────────────────────────────────────────────────

class ShortVideoSerializer(SupportLogicMixin, serializers.ModelSerializer):
    author_details   = serializers.SerializerMethodField()
    supporting_info  = serializers.SerializerMethodField()
    
    league_details   = serializers.SerializerMethodField()
    team_details     = serializers.SerializerMethodField()

    likes_count      = serializers.IntegerField(source='cached_likes',    read_only=True)
    comments_count   = serializers.IntegerField(source='cached_comments', read_only=True)
    shares_count     = serializers.IntegerField(source='cached_shares',   read_only=True)
    views_count      = serializers.IntegerField(source='cached_views',    read_only=True)

    video_url        = serializers.SerializerMethodField()
    thumbnail_url    = serializers.SerializerMethodField()
    is_liked         = serializers.SerializerMethodField()

    class Meta:
        model  = ShortVideo
        fields = [
            'id', 'author_details', 'video_url', 'thumbnail_url', 'caption',
            'league', 'league_details', 'team', 'team_details', 'supporting_info',
            'duration', 'duration_display', 'likes_count', 'comments_count',
            'shares_count', 'views_count', 'is_liked', 'created_at', 'status',
        ]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_author_details(self, obj):
        request = self.context.get('request')
        return _author_dict(obj.author, request)

    @extend_schema_field(OpenApiTypes.URI)
    def get_video_url(self, obj):
        request = self.context.get('request')
        path    = f"/api/videos/shorts/{obj.pk}/stream/"
        token   = request.auth.key if request and request.auth else None
        if token:
            path = f"{path}?token={token}"
        return request.build_absolute_uri(path) if request else path

    @extend_schema_field(OpenApiTypes.URI)
    def get_thumbnail_url(self, obj):
        request = self.context.get('request')
        return _build_url(request, obj.thumbnail)

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.likes.filter(user=request.user).exists()
        return False

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_league_details(self, obj):
        if obj.league_id and obj.league:
            return {
                'id':   obj.league.id,
                'name': obj.league.name,
                'logo': _build_url(None, obj.league.logo) if hasattr(obj.league, 'logo') else None,
            }
        return None

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_team_details(self, obj):
        if obj.team_id and obj.team:
            return {
                'id':   obj.team.id,
                'name': obj.team.name,
                'logo': _build_url(None, obj.team.logo) if hasattr(obj.team, 'logo') else None,
            }
        return None


# ─────────────────────────────────────────────────────────────────────────────
# SHORT VIDEO — WRITE
# ─────────────────────────────────────────────────────────────────────────────

class ShortVideoCreateSerializer(serializers.ModelSerializer):
    """
    Write serializer optimizing raw video ingestion payloads.
    Ensures that DRF handles file parsing streams correctly without discarding input metadata.
    """
    # ── FIXED CRITICAL WRITABLE WRAPPER (Follows Posts Pattern) ─────────────
    video = serializers.FileField(required=False, allow_null=True, allow_empty_file=True)
    file  = serializers.FileField(required=False, write_only=True, allow_null=True, allow_empty_file=True)

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
            raise serializers.ValidationError(f"Uploaded file must be a valid video stream. Received: {content_type}")
            
        max_size_bytes = 2 * 1024 * 1024 * 1024  # 2 GB
        if value.size > max_size_bytes:
            raise serializers.ValidationError("Video payload bounds exceed max limitations (2 GB).")
        return value


# ─────────────────────────────────────────────────────────────────────────────
# ENGAGEMENT (UTILITIES)
# ─────────────────────────────────────────────────────────────────────────────

class VideoLikeSerializer(serializers.ModelSerializer):
    class Meta:
        model  = VideoLike
        fields = ['id', 'video', 'created_at']
        read_only_fields = ['id', 'created_at']


class VideoShareSerializer(serializers.ModelSerializer):
    class Meta:
        model  = VideoShare
        fields = ['id', 'platform', 'created_at']
        read_only_fields = ['id', 'created_at']


class VideoViewSerializer(serializers.ModelSerializer):
    completed = serializers.BooleanField(read_only=True)

    class Meta:
        model  = VideoView
        fields = ['id', 'watch_time', 'completed', 'created_at']
        read_only_fields = ['id', 'completed', 'created_at']