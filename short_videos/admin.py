# short_videos/admin.py

from django.contrib import admin
from .models import (
    ShortVideo,
    VideoLike,
    VideoComment,
    CommentMention,
    VideoShare,
    VideoView,
)


@admin.register(ShortVideo)
class ShortVideoAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'author',
        'league',
        'team',
        'status',
        'duration',
        'cached_likes',
        'cached_comments',
        'cached_views',
        'created_at',
    )

    list_filter = (
        'status',
        'league',
        'team',
        'created_at',
    )

    search_fields = (
        'caption',
        'author__username',
    )

    readonly_fields = (
        'id',
        'cached_likes',
        'cached_comments',
        'cached_shares',
        'cached_views',
        'cached_avg_watch_ratio',
        'created_at',
        'updated_at',
    )

    ordering = ('-created_at',)


@admin.register(VideoComment)
class VideoCommentAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'author',
        'video',
        'short_content',
        'parent',
        'is_edited',
        'created_at',
    )

    search_fields = (
        'content',
        'author__username',
    )

    list_filter = (
        'is_edited',
        'created_at',
    )

    readonly_fields = (
        'id',
        'created_at',
    )

    ordering = ('-created_at',)

    def short_content(self, obj):
        if not obj.content:
            return ''
        return obj.content[:50]
    
    short_content.short_description = 'Content'


@admin.register(VideoLike)
class VideoLikeAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'video',
        'created_at',
    )

    search_fields = (
        'user__username',
    )

    ordering = ('-created_at',)


@admin.register(CommentMention)
class CommentMentionAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'comment',
        'user',
        'created_at',
    )

    search_fields = (
        'user__username',
    )

    ordering = ('-created_at',)


@admin.register(VideoShare)
class VideoShareAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'video',
        'platform',
        'created_at',
    )

    list_filter = (
        'platform',
    )

    ordering = ('-created_at',)


@admin.register(VideoView)
class VideoViewAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'video',
        'watch_time',
        'completed',
        'created_at',
    )

    list_filter = (
        'completed',
    )

    ordering = ('-created_at',)