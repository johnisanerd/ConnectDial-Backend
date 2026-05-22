# short_videos/serializers.py

import re

from django.contrib.auth import get_user_model
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import (
    CommentMention,
    ShortVideo,
    VideoComment,
    VideoLike,
    VideoShare,
    VideoView,
)

User = get_user_model()

_MENTION_RE = re.compile(r'@([\w.]+)')


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _build_url(request, file_field):

    if not file_field:
        return None

    try:
        url = file_field.url
    except Exception:
        return None

    return request.build_absolute_uri(url) if request else url


def _author_dict(user, request):

    if not user or user.is_anonymous:
        return {
            'id': None,
            'username': 'Anonymous',
            'display_name': 'Anonymous User',
            'profile_pic': None,
            'account_type': 'fan',
        }

    profile = getattr(user, 'profile', None)

    if not profile:
        profile = (
            getattr(user, 'userprofile', None)
            or getattr(user, 'user_profile', None)
        )

    profile_pic = _build_url(
        request,
        getattr(
            profile,
            'avatar',
            getattr(profile, 'profile_image', None)
        )
    )

    return {
        'id': user.id,
        'username': user.username,
        'display_name': (
            profile.display_name
            if profile and getattr(profile, 'display_name', None)
            else user.username
        ),
        'profile_pic': profile_pic,
        'account_type': getattr(user, 'account_type', 'fan'),
        'badge_type': getattr(user, 'badge_type', None),
    }


# ─────────────────────────────────────────────────────────────
# SUPPORT MIXIN
# ─────────────────────────────────────────────────────────────

class SupportLogicMixin:

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_supporting_info(self, obj):

        user = getattr(obj, 'author', getattr(obj, 'user', None))

        if not user or user.is_anonymous:
            return None

        if getattr(user, 'account_type', None) in (
            'news',
            'organization'
        ):
            return None

        target_league = getattr(obj, 'league', None)

        if not target_league and hasattr(obj, 'video'):
            target_league = getattr(obj.video, 'league', None)

        if target_league:

            pref = next(
                (
                    p for p in user.fan_preferences.all()
                    if p.league_id == target_league.id
                ),
                None,
            ) if hasattr(user, 'fan_preferences') else None

            if pref and pref.team:
                return {
                    'team_name': pref.team.name,
                    'team_logo': _build_url(None, pref.team.logo),
                    'league_name': target_league.name,
                    'type': 'contextual',
                }

        fav_team = getattr(user, 'favorite_team', None)
        fav_league = getattr(user, 'favorite_league', None)

        if fav_team:
            return {
                'team_name': fav_team.name,
                'team_logo': _build_url(None, fav_team.logo),
                'league_name': (
                    fav_league.name if fav_league else 'Global'
                ),
                'type': 'global',
            }

        return None


# ─────────────────────────────────────────────────────────────
# COMMENT SERIALIZERS
# ─────────────────────────────────────────────────────────────

class MentionedUserSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = ['id', 'username']


class CommentMentionSerializer(serializers.ModelSerializer):

    user = MentionedUserSerializer(read_only=True)

    class Meta:
        model = CommentMention
        fields = ['user']


class VideoCommentSerializer(
    SupportLogicMixin,
    serializers.ModelSerializer
):

    author_details = serializers.SerializerMethodField()
    supporting_info = serializers.SerializerMethodField()
    reply_count = serializers.SerializerMethodField()

    class Meta:
        model = VideoComment

        fields = [
            'id',
            'video',
            'parent',
            'content',
            'author_details',
            'supporting_info',
            'reply_count',
            'created_at',
            'updated_at',
            'is_edited',
        ]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_author_details(self, obj):

        request = self.context.get('request')

        return _author_dict(obj.author, request)

    @extend_schema_field(OpenApiTypes.INT)
    def get_reply_count(self, obj):

        return obj.replies.count()


class VideoCommentCreateSerializer(serializers.ModelSerializer):

    class Meta:
        model = VideoComment

        fields = [
            'id',
            'parent',
            'content',
        ]

        read_only_fields = ['id']

        extra_kwargs = {
            'parent': {
                'required': False,
                'allow_null': True,
            }
        }

    def validate_content(self, value):

        value = (value or '').strip()

        if not value:
            raise serializers.ValidationError(
                "Comment cannot be empty."
            )

        if len(value) > 1000:
            raise serializers.ValidationError(
                "Comment too long."
            )

        return value

    def validate_parent(self, value):

        if value and value.parent_id is not None:
            raise serializers.ValidationError(
                "Nested replies disabled."
            )

        return value


# ─────────────────────────────────────────────────────────────
# SHORT VIDEO READ
# ─────────────────────────────────────────────────────────────

class ShortVideoSerializer(
    SupportLogicMixin,
    serializers.ModelSerializer
):

    author_details = serializers.SerializerMethodField()

    supporting_info = serializers.SerializerMethodField()

    league_details = serializers.SerializerMethodField()

    team_details = serializers.SerializerMethodField()

    likes_count = serializers.IntegerField(
        source='cached_likes',
        read_only=True
    )

    comments_count = serializers.IntegerField(
        source='cached_comments',
        read_only=True
    )

    shares_count = serializers.IntegerField(
        source='cached_shares',
        read_only=True
    )

    views_count = serializers.IntegerField(
        source='cached_views',
        read_only=True
    )

    video_url = serializers.SerializerMethodField()

    thumbnail_url = serializers.SerializerMethodField()

    is_liked = serializers.SerializerMethodField()

    class Meta:
        model = ShortVideo

        fields = [
            'id',
            'author_details',
            'video_url',
            'thumbnail_url',
            'caption',
            'league',
            'league_details',
            'team',
            'team_details',
            'supporting_info',
            'duration',
            'duration_display',
            'likes_count',
            'comments_count',
            'shares_count',
            'views_count',
            'is_liked',
            'created_at',
            'status',
        ]

    def get_author_details(self, obj):

        request = self.context.get('request')

        return _author_dict(obj.author, request)

    def get_video_url(self, obj):

        request = self.context.get('request')

        path = f"/api/videos/shorts/{obj.pk}/stream/"

        token = None
        if request and request.auth:
            if hasattr(request.auth, 'key'):
                token = request.auth.key
            elif isinstance(request.auth, str):
                token = request.auth

        if token:
            path = f"{path}?token={token}"

        return (
            request.build_absolute_uri(path)
            if request else path
        )

    def get_thumbnail_url(self, obj):

        request = self.context.get('request')

        return _build_url(request, obj.thumbnail)

    def get_is_liked(self, obj):

        request = self.context.get('request')

        if request and request.user.is_authenticated:
            return obj.likes.filter(
                user=request.user
            ).exists()

        return False

    def get_league_details(self, obj):

        if obj.league_id and obj.league:
            return {
                'id': obj.league.id,
                'name': obj.league.name,
                'logo': _build_url(
                    None,
                    obj.league.logo
                ) if hasattr(obj.league, 'logo') else None,
            }

        return None

    def get_team_details(self, obj):

        if obj.team_id and obj.team:
            return {
                'id': obj.team.id,
                'name': obj.team.name,
                'logo': _build_url(
                    None,
                    obj.team.logo
                ) if hasattr(obj.team, 'logo') else None,
            }

        return None


# ─────────────────────────────────────────────────────────────
# SHORT VIDEO CREATE
# ─────────────────────────────────────────────────────────────

class ShortVideoCreateSerializer(serializers.ModelSerializer):

    video = serializers.FileField(
        required=False,
        allow_null=True,
        allow_empty_file=True
    )

    file = serializers.FileField(
        required=False,
        write_only=True,
        allow_null=True,
        allow_empty_file=True
    )

    class Meta:
        model = ShortVideo

        fields = [
            'caption',
            'league',
            'team',
            'video',
            'file',
        ]

    def validate(self, attrs):

        if 'file' in attrs and not attrs.get('video'):
            attrs['video'] = attrs.pop('file')
        else:
            attrs.pop('file', None)

        return attrs

    def validate_video(self, value):

        if not value:
            return value

        content_type = (
            getattr(value, 'content_type', '')
            or ''
        )

        if (
            content_type and
            not content_type.startswith('video/')
        ):
            raise serializers.ValidationError(
                f"Invalid video type: {content_type}"
            )

        max_size_bytes = 2 * 1024 * 1024 * 1024

        if value.size > max_size_bytes:
            raise serializers.ValidationError(
                "Video exceeds 2 GB limit."
            )

        return value


# ─────────────────────────────────────────────────────────────
# ENGAGEMENT
# ─────────────────────────────────────────────────────────────

class VideoLikeSerializer(serializers.ModelSerializer):

    class Meta:
        model = VideoLike

        fields = [
            'id',
            'video',
            'created_at',
        ]

        read_only_fields = [
            'id',
            'created_at',
        ]


class VideoShareSerializer(serializers.ModelSerializer):

    class Meta:
        model = VideoShare

        fields = [
            'id',
            'platform',
            'created_at',
        ]

        read_only_fields = [
            'id',
            'created_at',
        ]


class VideoViewSerializer(serializers.ModelSerializer):

    completed = serializers.BooleanField(read_only=True)

    class Meta:
        model = VideoView

        fields = [
            'id',
            'watch_time',
            'completed',
            'created_at',
        ]

        read_only_fields = [
            'id',
            'completed',
            'created_at',
        ]