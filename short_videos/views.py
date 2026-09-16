"""
ConnectDial — Short Video Views (Optimized Final)
=================================================
Endpoints
─────────
Feed
  GET  /api/videos/shorts/feed/                              personalised feed

Upload
  POST /api/videos/shorts/upload/                            upload short video

Streaming
  GET  /api/videos/shorts/<pk>/stream/                       HTTP Range stream

Engagement
  POST /api/videos/shorts/<pk>/like/                         toggle like
  POST /api/videos/shorts/<pk>/view/                         record view
  POST /api/videos/shorts/<pk>/share/                        external share
  POST /api/videos/shorts/<pk>/reshare/                      in-app reshare toggle

Comments
  GET  /api/videos/shorts/<pk>/comments/                     list top-level comments
  POST /api/videos/shorts/<pk>/comments/                     create comment
  GET  /api/videos/shorts/<pk>/comments/<comment_pk>/replies/ list replies
  PATCH/DELETE /api/videos/comments/<pk>/                    edit/delete own comment
"""

# ── stdlib ────────────────────────────────────────────────────────────────────
import threading
from urllib.parse import quote

# ── Django ────────────────────────────────────────────────────────────────────
from django.contrib.auth import get_user_model
from django.db.models import F
from django.shortcuts import get_object_or_404
from connectdial.media import build_media_url

# ── DRF ──────────────────────────────────────────────────────────────────────
from rest_framework import generics, status
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.generics import ListAPIView
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView

# ── Local ─────────────────────────────────────────────────────────────────────
from .models import ShortVideo, VideoComment, VideoLike, VideoShare, VideoView
from .serializers import (
    ShortVideoSerializer,
    ShortVideoCreateSerializer,
    VideoCommentCreateSerializer,
    VideoCommentSerializer,
    VideoShareSerializer,
    VideoViewSerializer,
)
from .streaming import (
    build_telegram_share_text,
    build_whatsapp_share_text,
    stream_video_response,
)

User = get_user_model()



def _request_data_as_dict(request_data):
    """
    Convert request.data to a plain Python dict.
    Django's QueryDict (used for form/multipart requests) stores every value
    as a list — .dict() collapses each to its last value.
    """

    if hasattr(request_data, 'dict'):
        return request_data.dict()

    return dict(request_data)

class ShortVideoUploadView(generics.CreateAPIView):

    serializer_class = ShortVideoCreateSerializer

    permission_classes = [IsAuthenticated]

    parser_classes = [MultiPartParser, FormParser]

    def create(self, request, *args, **kwargs):

        serializer = self.get_serializer(data=request.data)

        serializer.is_valid(raise_exception=True)

        try:

            instance = self.perform_create(serializer)

        except Exception as exc:

            if any(
                x in str(exc).lower()
                for x in ["too large", "2gb", "maximum"]
            ):

                return Response(
                    {
                        "video": [
                            "Video file is too large. Maximum allowed size is 2 GB."
                        ]
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            raise

        instance.refresh_from_db()

        read_serializer = ShortVideoSerializer(
            instance,
            context={'request': request}
        )

        return Response(
            read_serializer.data,
            status=status.HTTP_201_CREATED
        )

    def perform_create(self, serializer):

        video_file = (
            self.request.FILES.get('file')
            or self.request.FILES.get('video')
        )

        # ─────────────────────────────────────────────
        # LEAGUE
        # ─────────────────────────────────────────────

        league = None

        league_id = (
            self.request.data.get('league_id')
            or self.request.data.get('league')
        )

        if league_id:

            try:

                from leagues.models import League

                league = League.objects.get(pk=league_id)

            except Exception:
                pass

        # ─────────────────────────────────────────────
        # TEAM
        # ─────────────────────────────────────────────

        team = None

        team_id = (
            self.request.data.get('team_id')
            or self.request.data.get('team')
        )

        if team_id:

            try:

                from leagues.models import Team

                team = Team.objects.get(pk=team_id)

            except Exception:
                pass

        # ─────────────────────────────────────────────
        # FAST SAVE
        # ─────────────────────────────────────────────

        instance = serializer.save(
            author=self.request.user,
            duration=0,
            league=league,
            team=team,
            status='processing',
            video=video_file,
        )

        # ─────────────────────────────────────────────
        # BACKGROUND PROCESSING
        # ─────────────────────────────────────────────

        try:

            from .tasks import process_short_video

            process_short_video.delay(str(instance.pk))

        except Exception:

            t = threading.Thread(
                target=self._process_in_background,
                args=(instance.pk,),
                daemon=True,
            )

            t.start()

        return instance

    def _process_in_background(self, video_pk):
        """Fallback when the Celery broker is temporarily unavailable.

        Uses the same storage-safe processing path as the Celery worker instead
        of accessing ``FieldFile.path`` (which does not exist for remote object storage).
        """
        try:
            from .tasks import process_short_video
            process_short_video.run(str(video_pk))
        except Exception:
            # The task itself records failed status; do not publish raw media.
            pass


# ─────────────────────────────────────────────────────────────────────────────
# FEED
# ─────────────────────────────────────────────────────────────────────────────

class ShortVideoPagination(LimitOffsetPagination):
    default_limit = 20
    max_limit     = 50


class ShortVideoFeedView(ListAPIView):
    """
    GET /api/videos/shorts/feed/
    Query params:
      league_id  – filter to league (int / uuid)
      team_id    – filter to team   (int / uuid)
      limit      – page size (default 20, max 50)
      offset     – pagination offset
    """

    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes     = [IsAuthenticatedOrReadOnly]
    serializer_class       = ShortVideoSerializer
    pagination_class       = ShortVideoPagination

    # ── Annotate liked status in one query so serializer avoids N+1 ──────────
    def _annotate_liked(self, qs_or_list, user):
        """
        Attach an `_is_liked` boolean attribute to each ShortVideo object so
        ShortVideoSerializer.get_is_liked() can read it without a per-item DB hit.
        """
        if not user or not user.is_authenticated:
            for v in qs_or_list:
                v._is_liked = False
            return qs_or_list

        from .models import VideoLike
        liked_ids = set(
            VideoLike.objects
            .filter(user=user, video__in=qs_or_list)
            .values_list('video_id', flat=True)
        )
        for v in qs_or_list:
            v._is_liked = v.pk in liked_ids
        return qs_or_list

    def get_queryset(self):
        """
        Returns a plain list (from feed algorithm) or a QuerySet (guest path).
        DRF pagination handles both via list().
        """
        user      = self.request.user
        league_id = self.request.query_params.get('league_id') or None
        team_id   = self.request.query_params.get('team_id')   or None

        # Normalise empty strings
        if league_id == '':
            league_id = None
        if team_id == '':
            team_id = None

        if user and user.is_authenticated:
            from .feed_algorithm import get_short_video_feed
            result = get_short_video_feed(
                user,
                league_id=league_id,
                team_id=team_id,
            )
            return self._annotate_liked(result, user)

        # Guest: simple chronological QuerySet
        qs = (
            ShortVideo.objects
            .filter(status='published')
            .select_related('author', 'author__profile', 'league', 'team')
        )
        if league_id:
            qs = qs.filter(league_id=league_id)
        if team_id:
            qs = qs.filter(team_id=team_id)

        result = list(qs.order_by('-created_at'))
        return self._annotate_liked(result, user)

    # DRF's ListAPIView.list() calls get_queryset() then paginate_queryset().
    # paginate_queryset() works fine with plain lists.
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['request'] = self.request
        return ctx


# ─────────────────────────────────────────────────────────────────────────────
# STREAMING
# ─────────────────────────────────────────────────────────────────────────────

class ShortVideoStreamView(APIView):

    authentication_classes = [
        TokenAuthentication,
        SessionAuthentication
    ]

    permission_classes = [IsAuthenticatedOrReadOnly]

    def get(self, request, pk):

        video = get_object_or_404(ShortVideo, pk=pk)

        return stream_video_response(request, video)


# ─────────────────────────────────────────────────────────────────────────────
# ENGAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

class VideoLikeToggleView(APIView):

    authentication_classes = [
        TokenAuthentication,
        SessionAuthentication
    ]

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):

        video = get_object_or_404(ShortVideo, pk=pk)

        like = VideoLike.objects.filter(
            user=request.user,
            video=video
        ).first()

        if like:

            like.delete()

            # post_delete signal updates cached_likes atomically.
            video.refresh_from_db(fields=['cached_likes'])

            return Response(
                {
                    'liked': False,
                    'likes_count': max(video.cached_likes, 0)
                },
                status=status.HTTP_200_OK,
            )

        VideoLike.objects.create(
            user=request.user,
            video=video
        )

        # post_save signal updates cached_likes atomically.
        video.refresh_from_db(fields=['cached_likes'])

        return Response(
            {
                'liked': True,
                'likes_count': video.cached_likes
            },
            status=status.HTTP_201_CREATED,
        )




class VideoViewRecordView(APIView):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes     = [IsAuthenticated]

    def post(self, request, pk):
        video = get_object_or_404(ShortVideo, pk=pk)

        data = _request_data_as_dict(request.data)
        data.pop('video', None)

        serializer = VideoViewSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user, video=video)

        # VideoView post_save signal updates cached_views and watch ratio.
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class VideoShareRecordView(APIView):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes     = [IsAuthenticated]

    @staticmethod
    def _share_url(video) -> str:
        """Absolute share URL — uses model property if available, else builds it."""
        if hasattr(video, 'share_url') and video.share_url:
            return video.share_url
        return f"https://api.connectdial.com/shorts/{video.pk}/"

    @staticmethod
    def _og_title(video) -> str:
        if hasattr(video, 'og_title') and video.og_title:
            return video.og_title
        author = getattr(video, 'author', None)
        username = getattr(author, 'username', 'user') if author else 'user'
        caption  = (video.caption or '')[:60]
        return f"{caption} – @{username}" if caption else f"Video by @{username}"

    @staticmethod
    def _og_description(video) -> str:
        if hasattr(video, 'og_description') and video.og_description:
            return video.og_description
        return (video.caption or '')[:160]

    def post(self, request, pk):
        video = get_object_or_404(ShortVideo, pk=pk)

        data = _request_data_as_dict(request.data)
        data.pop('video', None)

        serializer = VideoShareSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        share = serializer.save(user=request.user, video=video)

        # VideoShare post_save signal updates cached_shares.
        video.refresh_from_db(fields=['cached_shares'])

        share_url   = self._share_url(video)
        og_title    = self._og_title(video)
        og_desc     = self._og_description(video)
        platform    = share.platform

        payload = {
            **serializer.data,
            'shares_count':   video.cached_shares,
            'share_url':      share_url,
            'og_title':       og_title,
            'og_description': og_desc,
            'thumbnail_url': (
                build_media_url(video.thumbnail, request)
                if video.thumbnail else None
            ),
        }

        if platform == 'whatsapp':
            text = build_whatsapp_share_text(video, share_url)
            payload['text']         = text
            payload['whatsapp_url'] = f"https://wa.me/?text={quote(text)}"
        elif platform == 'telegram':
            text = build_telegram_share_text(video, share_url)
            payload['text']         = text
            payload['telegram_url'] = (
                f"https://t.me/share/url?url={quote(share_url)}"
                f"&text={quote(og_title)}"
            )
        elif platform == 'twitter':
            payload['twitter_url'] = (
                f"https://twitter.com/intent/tweet"
                f"?url={quote(share_url)}&text={quote(og_title)}"
            )

        return Response(payload, status=status.HTTP_201_CREATED)


class VideoReshareView(APIView):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes     = [IsAuthenticated]

    def post(self, request, pk):
        video    = get_object_or_404(ShortVideo, pk=pk)
        existing = VideoShare.objects.filter(
            user=request.user, video=video, platform='reshare'
        ).first()

        if existing:
            existing.delete()  # post_delete signal decrements cached_shares
            return Response({'reshared': False}, status=status.HTTP_200_OK)

        VideoShare.objects.create(user=request.user, video=video, platform='reshare')
        # post_save signal increments cached_shares
        return Response({'reshared': True}, status=status.HTTP_201_CREATED)


# ─────────────────────────────────────────────────────────────────────────────
# COMMENTS
# ─────────────────────────────────────────────────────────────────────────────

class VideoCommentListCreateView(APIView):
    """
    GET  /api/videos/shorts/<pk>/comments/
    POST /api/videos/shorts/<pk>/comments/
    """
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes     = [IsAuthenticatedOrReadOnly]

    def _annotate_comment_likes(self, comments, user):
        """
        Attach _is_liked to each comment in one query (avoids N+1).
        Also sets _likes_count from the pre-fetched reverse relation.
        """
        if not user or not user.is_authenticated:
            for c in comments:
                c._is_liked = False
                c._likes_count = 0
            return comments

        from .models import VideoCommentLike
        liked_ids = set(
            VideoCommentLike.objects
            .filter(user=user, comment__in=comments)
            .values_list('comment_id', flat=True)
        )
        for c in comments:
            c._is_liked = c.pk in liked_ids
            c._likes_count = getattr(c, 'cached_likes', 0)
        return comments

    def get(self, request, pk):
        video = get_object_or_404(ShortVideo, pk=pk)

        qs = list(
            VideoComment.objects
            .filter(video=video, parent__isnull=True)
            .select_related(
                'author',
                'author__profile',
                'video',
                'video__league',
            )
            .prefetch_related(
                'author__fan_preferences',
                'author__fan_preferences__team',
                'replies',
            )
            .order_by('-created_at')
        )

        self._annotate_comment_likes(qs, request.user)

        serializer = VideoCommentSerializer(qs, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, pk):
        video = get_object_or_404(ShortVideo, pk=pk)

        data = _request_data_as_dict(request.data)
        data.pop('video', None)

        serializer = VideoCommentCreateSerializer(data=data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        comment = serializer.save(author=request.user, video=video)
        # VideoComment post_save signal increments cached_comments.

        # Re-fetch with related data so the response has full author/supporting_info
        comment = (
            VideoComment.objects
            .select_related('author', 'author__profile', 'video', 'video__league')
            .prefetch_related('author__fan_preferences', 'author__fan_preferences__team')
            .get(pk=comment.pk)
        )
        comment._is_liked    = False
        comment._likes_count = 0

        return Response(
            VideoCommentSerializer(comment, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


class CommentRepliesListView(ListAPIView):
    """
    GET /api/videos/shorts/<pk>/comments/<comment_pk>/replies/
    """
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes     = [IsAuthenticatedOrReadOnly]
    serializer_class       = VideoCommentSerializer

    def get_queryset(self):
        return list(
            VideoComment.objects
            .filter(
                video_id=self.kwargs['pk'],
                parent_id=self.kwargs['comment_pk'],
            )
            .select_related('author', 'author__profile', 'video', 'video__league')
            .prefetch_related('author__fan_preferences', 'author__fan_preferences__team')
            .order_by('created_at')
        )

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()

        # Annotate like status in one query
        if request.user.is_authenticated:
            from .models import VideoCommentLike
            liked_ids = set(
                VideoCommentLike.objects
                .filter(user=request.user, comment__in=qs)
                .values_list('comment_id', flat=True)
            )
            for c in qs:
                c._is_liked    = c.pk in liked_ids
                c._likes_count = getattr(c, 'cached_likes', 0)
        else:
            for c in qs:
                c._is_liked    = False
                c._likes_count = 0

        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['request'] = self.request
        return ctx


class CommentDetailView(APIView):
    """
    PATCH  /api/videos/comments/<pk>/
    DELETE /api/videos/comments/<pk>/
    """
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes     = [IsAuthenticated]

    def _get_own_comment(self, request, pk):
        comment = get_object_or_404(VideoComment, pk=pk)
        if comment.author_id != request.user.id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('You do not own this comment.')
        return comment

    def patch(self, request, pk):
        comment = self._get_own_comment(request, pk)
        data = _request_data_as_dict(request.data)
        data.pop('video', None)

        serializer = VideoCommentCreateSerializer(
            comment, data=data, partial=True, context={'request': request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        updated = serializer.save(is_edited=True)
        updated._is_liked    = False
        updated._likes_count = 0
        return Response(
            VideoCommentSerializer(updated, context={'request': request}).data,
            status=status.HTTP_200_OK,
        )

    def delete(self, request, pk):
        comment = self._get_own_comment(request, pk)
        comment.delete()  # post_delete signal decrements cached_comments
        return Response(status=status.HTTP_204_NO_CONTENT)


class VideoCommentLikeToggleView(APIView):
    """
    POST /api/videos/comments/<pk>/like/
    Toggles a like on a comment. Returns { liked: bool, likes_count: int }.
    """
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes     = [IsAuthenticated]

    def post(self, request, pk):
        from .models import VideoCommentLike

        comment = get_object_or_404(VideoComment, pk=pk)
        existing = VideoCommentLike.objects.filter(
            user=request.user, comment=comment
        ).first()

        if existing:
            existing.delete()
            # Decrement cached counter safely
            VideoComment.objects.filter(pk=pk).update(
                cached_likes=F('cached_likes') - 1
            )
            comment.refresh_from_db(fields=['cached_likes'])
            return Response(
                {'liked': False, 'likes_count': max(comment.cached_likes, 0)},
                status=status.HTTP_200_OK,
            )

        VideoCommentLike.objects.create(user=request.user, comment=comment)
        VideoComment.objects.filter(pk=pk).update(
            cached_likes=F('cached_likes') + 1
        )
        comment.refresh_from_db(fields=['cached_likes'])
        return Response(
            {'liked': True, 'likes_count': comment.cached_likes},
            status=status.HTTP_201_CREATED,
        )