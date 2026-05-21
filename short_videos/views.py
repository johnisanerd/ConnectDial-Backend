"""
ConnectDial — Views (Final)
============================
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

Key fix
───────
  All write serializers (VideoCommentCreateSerializer, VideoShareSerializer,
  VideoViewSerializer) no longer have a 'video' field.  The resolved video
  ORM instance is passed directly to serializer.save(video=video), bypassing
  PrimaryKeyRelatedField / UUID parsing entirely — the root cause of the 500s.
"""

# ── stdlib ────────────────────────────────────────────────────────────────────
import os
import tempfile
import threading
from urllib.parse import quote

# ── Django ────────────────────────────────────────────────────────────────────
from django.contrib.auth import get_user_model
from django.core.files import File
from django.core.files.base import ContentFile
from django.db.models import F
from django.shortcuts import get_object_or_404

# ── DRF ──────────────────────────────────────────────────────────────────────
from rest_framework import generics, status
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.generics import ListAPIView
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView

# ── Local ─────────────────────────────────────────────────────────────────────
from .feed_algorithm import get_short_video_feed
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
from .video_processing import (
    compress_video,
    extract_duration,
    generate_thumbnail,
)

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _request_data_as_dict(request_data):
    """
    Convert request.data to a plain Python dict.
    Django's QueryDict (used for form/multipart requests) stores every value
    as a list — .dict() collapses each to its last value, which is correct
    for all single-value fields we use (content, watch_time, platform, …).
    JSON request bodies are already plain dicts.
    """
    if hasattr(request_data, 'dict'):
        return request_data.dict()
    return dict(request_data)


# ─────────────────────────────────────────────────────────────────────────────
# UPLOAD
# ─────────────────────────────────────────────────────────────────────────────

class ShortVideoUploadView(generics.CreateAPIView):
    serializer_class   = ShortVideoCreateSerializer
    permission_classes = [IsAuthenticated]
    parser_classes     = [MultiPartParser, FormParser]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            instance = self.perform_create(serializer)
        except Exception as exc:
            if any(x in str(exc).lower() for x in ["too large", "2gb", "maximum"]):
                return Response(
                    {"video": ["Video file is too large. Maximum allowed size is 2 GB."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            raise

        instance.refresh_from_db()
        read_serializer = ShortVideoSerializer(instance, context={'request': request})
        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        video_file = self.request.FILES.get('file') or self.request.FILES.get('video')

        league    = None
        league_id = self.request.data.get('league_id') or self.request.data.get('league')
        if league_id:
            try:
                from leagues.models import League
                league = League.objects.get(pk=league_id)
            except Exception:
                pass

        tmp_path = None
        if video_file:
            suffix = os.path.splitext(video_file.name or '')[-1] or '.mp4'
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                for chunk in video_file.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name

        instance = serializer.save(
            author=self.request.user,
            duration=0,
            league=league,
            status='draft',
        )

        if tmp_path:
            try:
                from .tasks import process_short_video
                process_short_video.delay(str(instance.pk), tmp_path)
            except Exception:
                t = threading.Thread(
                    target=self._save_raw_and_publish,
                    args=(instance, tmp_path),
                    daemon=True,
                )
                t.start()

        return instance

    def _save_raw_and_publish(self, instance, tmp_path):
        try:
            duration = extract_duration(tmp_path)
            with open(tmp_path, 'rb') as f:
                instance.video.save(os.path.basename(tmp_path), File(f), save=False)
            instance.duration = duration
            instance.status   = 'published'
            instance.save(update_fields=['video', 'duration', 'status'])
            try:
                thumb_bytes = generate_thumbnail(tmp_path)
                instance.thumbnail.save(
                    f'thumb_{instance.pk}.jpg',
                    ContentFile(thumb_bytes),
                    save=True,
                )
            except Exception:
                pass
        except Exception:
            instance.status = 'published'
            instance.save(update_fields=['status'])
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass


# ─────────────────────────────────────────────────────────────────────────────
# FEED
# ─────────────────────────────────────────────────────────────────────────────

class ShortVideoPagination(LimitOffsetPagination):
    default_limit = 10
    max_limit     = 20


class ShortVideoFeedView(ListAPIView):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes     = [IsAuthenticated]
    serializer_class       = ShortVideoSerializer
    pagination_class       = ShortVideoPagination

    def get_queryset(self):
        bypass = bool(self.request.query_params.get('bypass_cache', False))
        return get_short_video_feed(self.request.user, bypass_cache=bypass)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['request'] = self.request
        return ctx


# ─────────────────────────────────────────────────────────────────────────────
# STREAMING
# ─────────────────────────────────────────────────────────────────────────────

class ShortVideoStreamView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes     = []

    def get(self, request, pk):
        user = request.user

        if not user.is_authenticated:
            token_key = request.query_params.get('token', '').strip()
            if token_key:
                try:
                    token_obj = Token.objects.select_related('user').get(key=token_key)
                    user = token_obj.user
                except Token.DoesNotExist:
                    return Response(
                        {"detail": "Invalid token."},
                        status=status.HTTP_401_UNAUTHORIZED,
                    )

        if not user.is_authenticated:
            return Response(
                {"detail": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        video = get_object_or_404(ShortVideo, pk=pk)
        return stream_video_response(request, video)


# ─────────────────────────────────────────────────────────────────────────────
# ENGAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

class VideoLikeToggleView(APIView):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes     = [IsAuthenticated]

    def post(self, request, pk):
        video = get_object_or_404(ShortVideo, pk=pk)
        like, created = VideoLike.objects.get_or_create(user=request.user, video=video)

        if created:
            ShortVideo.objects.filter(pk=pk).update(cached_likes=F('cached_likes') + 1)
            video.refresh_from_db(fields=['cached_likes'])
            return Response(
                {'liked': True, 'likes_count': video.cached_likes},
                status=status.HTTP_201_CREATED,
            )

        like.delete()
        ShortVideo.objects.filter(pk=pk).update(cached_likes=F('cached_likes') - 1)
        video.refresh_from_db(fields=['cached_likes'])
        return Response(
            {'liked': False, 'likes_count': max(video.cached_likes, 0)},
            status=status.HTTP_200_OK,
        )


class VideoViewRecordView(APIView):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes     = [IsAuthenticated]

    def post(self, request, pk):
        video = get_object_or_404(ShortVideo, pk=pk)

        # Pass only non-video fields; video instance injected via save()
        data = _request_data_as_dict(request.data)
        data.pop('video', None)   # prevent any stale value from the client

        serializer = VideoViewSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user, video=video)

        ShortVideo.objects.filter(pk=pk).update(cached_views=F('cached_views') + 1)

        return Response(serializer.data, status=status.HTTP_201_CREATED)


class VideoShareRecordView(APIView):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes     = [IsAuthenticated]

    def post(self, request, pk):
        video = get_object_or_404(ShortVideo, pk=pk)

        data = _request_data_as_dict(request.data)
        data.pop('video', None)

        serializer = VideoShareSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        share = serializer.save(user=request.user, video=video)

        ShortVideo.objects.filter(pk=pk).update(cached_shares=F('cached_shares') + 1)
        video.refresh_from_db(fields=['cached_shares'])

        platform = share.platform
        payload  = {
            **serializer.data,
            'shares_count':  video.cached_shares,
            'share_url':     video.share_url,
            'og_title':      video.og_title,
            'og_description': video.og_description,
            'thumbnail_url': (
                request.build_absolute_uri(video.thumbnail.url)
                if video.thumbnail else None
            ),
        }

        if platform == 'whatsapp':
            text = build_whatsapp_share_text(video)
            payload['text']          = text
            payload['whatsapp_url']  = f"https://wa.me/?text={quote(text)}"
        elif platform == 'telegram':
            text = build_telegram_share_text(video)
            payload['text']          = text
            payload['telegram_url']  = (
                f"https://t.me/share/url?url={quote(video.share_url)}"
                f"&text={quote(video.og_title)}"
            )
        elif platform == 'twitter':
            payload['twitter_url'] = (
                f"https://twitter.com/intent/tweet"
                f"?url={quote(video.share_url)}&text={quote(video.og_title)}"
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
            existing.delete()
            ShortVideo.objects.filter(pk=pk).update(cached_shares=F('cached_shares') - 1)
            return Response({'reshared': False}, status=status.HTTP_200_OK)

        VideoShare.objects.create(user=request.user, video=video, platform='reshare')
        ShortVideo.objects.filter(pk=pk).update(cached_shares=F('cached_shares') + 1)
        return Response({'reshared': True}, status=status.HTTP_201_CREATED)


# ─────────────────────────────────────────────────────────────────────────────
# COMMENTS
# ─────────────────────────────────────────────────────────────────────────────
# views.py
# =============================================================================

# views.py
# =============================================================================

class VideoCommentListCreateView(APIView):
    # Fix: Ensure BOTH authentication engines are paired so unauthenticated list reads
    # and authenticated user write payloads are verified flawlessly without dropping into 500s.
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get(self, request, pk):
        # 1. Make sure the video instance exists safely
        video = get_object_or_404(ShortVideo, pk=pk)

        # 2. Pull root comments using a stable, single join query setup
        qs = (
            VideoComment.objects
            .filter(video=video, parent__isnull=True)
            .select_related('author') # Clean single join, no unstable double profiles
            .prefetch_related('mentions__user', 'replies')
            .order_by('created_at')
        )

        # 3. Serialize data cleanly
        serializer = VideoCommentSerializer(qs, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def post(self, request, pk):
        video = get_object_or_404(ShortVideo, pk=pk)

        # Strip 'video' out of raw incoming client payloads to honor write structures
        data = _request_data_as_dict(request.data)
        data.pop('video', None)

        serializer = VideoCommentCreateSerializer(
            data=data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)

        # Pass your clean ORM instance straight into the save method
        comment = serializer.save(author=request.user, video=video)

        # Atomically increment your denormalized cached values
        ShortVideo.objects.filter(pk=pk).update(cached_comments=F('cached_comments') + 1)

        return Response(
            VideoCommentSerializer(comment, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )

class CommentRepliesListView(ListAPIView):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes     = [IsAuthenticatedOrReadOnly]
    serializer_class       = VideoCommentSerializer

    def get_queryset(self):
        return (
            VideoComment.objects
            .filter(
                video_id=self.kwargs['pk'],
                parent_id=self.kwargs['comment_pk'],
            )
            .select_related('author', 'author__profile')
            .prefetch_related('mentions__user')
            .order_by('created_at')
        )


class CommentDetailView(APIView):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes     = [IsAuthenticated]

    def _get_own_comment(self, request, pk):
        comment = get_object_or_404(VideoComment, pk=pk)
        if comment.author_id != request.user.pk:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You can only edit or delete your own comments.")
        return comment

    def patch(self, request, pk):
        comment = self._get_own_comment(request, pk)

        data = _request_data_as_dict(request.data)
        data.pop('video', None)

        serializer = VideoCommentCreateSerializer(
            comment,
            data=data,
            partial=True,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        updated = serializer.save(is_edited=True)
        return Response(
            VideoCommentSerializer(updated, context={'request': request}).data
        )

    def delete(self, request, pk):
        comment  = self._get_own_comment(request, pk)
        video_pk = comment.video_id
        comment.delete()
        ShortVideo.objects.filter(pk=video_pk).update(
            cached_comments=F('cached_comments') - 1
        )
        return Response(status=status.HTTP_204_NO_CONTENT)