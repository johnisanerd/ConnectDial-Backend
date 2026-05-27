from django.urls import path
from . import views
from .admin_views import HighlightlyImportView

urlpatterns = [
    # ── Feed ──────────────────────────────────────────────────────────────────
    path('shorts/feed/', views.ShortVideoFeedView.as_view(), name='short-video-feed'),

    # ── Upload ────────────────────────────────────────────────────────────────
    path('shorts/upload/', views.ShortVideoUploadView.as_view(), name='short-video-upload'),

    # ── Streaming ─────────────────────────────────────────────────────────────
    path('shorts/<uuid:pk>/stream/', views.ShortVideoStreamView.as_view(), name='short-video-stream'),

    # ── Video engagement ──────────────────────────────────────────────────────
    path('shorts/<uuid:pk>/like/',    views.VideoLikeToggleView.as_view(),  name='short-video-like'),
    path('shorts/<uuid:pk>/view/',    views.VideoViewRecordView.as_view(),  name='short-video-view'),
    path('shorts/<uuid:pk>/share/',   views.VideoShareRecordView.as_view(), name='short-video-share'),
    path('shorts/<uuid:pk>/reshare/', views.VideoReshareView.as_view(),     name='short-video-reshare'),

    # ── Comments ──────────────────────────────────────────────────────────────
    path('shorts/<uuid:pk>/comments/',
         views.VideoCommentListCreateView.as_view(),
         name='short-video-comments'),

    path('shorts/<uuid:pk>/comments/<uuid:comment_pk>/replies/',
         views.CommentRepliesListView.as_view(),
         name='short-video-comment-replies'),

    # ── Individual comment management ─────────────────────────────────────────
    path('comments/<uuid:pk>/',
         views.CommentDetailView.as_view(),
         name='comment-detail'),

    # ── Comment like toggle ───────────────────────────────────────────────────
    # POST → toggles like; returns { liked: bool, likes_count: int }
    path('comments/<uuid:pk>/like/',
         views.VideoCommentLikeToggleView.as_view(),
         name='comment-like'),

    # ── Superadmin import ─────────────────────────────────────────────────────
    path('admin/import-highlights/',
         HighlightlyImportView.as_view(),
         name='admin-import-highlights'),
]