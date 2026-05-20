"""
ConnectDial — Views
====================
Endpoints
─────────
Feed
  GET  /api/videos/shorts/feed/                              personalised short-video feed

Upload
  POST /api/videos/shorts/upload/                            upload a new short video

Streaming
  GET  /api/videos/shorts/<pk>/stream/                       HTTP Range-aware video stream

... (all other endpoints)
"""

# ── stdlib ────────────────────────────────────────────────────────────────────
import io
import os
import tempfile
from urllib.parse import quote

# ── Django ────────────────────────────────────────────────────────────────────
from django.contrib.auth import get_user_model
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.shortcuts import get_object_or_404

# ── DRF ──────────────────────────────────────────────────────────────────────
from rest_framework import generics, status
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.generics import ListAPIView
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import (
    IsAuthenticated,
    IsAuthenticatedOrReadOnly,
)
from rest_framework.response import Response
from rest_framework.views import APIView

# ── Local ─────────────────────────────────────────────────────────────────────
from .feed_algorithm import get_short_video_feed, FEED_FETCH_SIZE
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
# UPLOAD
# ─────────────────────────────────────────────────────────────────────────────

class ShortVideoUploadView(generics.CreateAPIView):
    """
    POST /api/videos/shorts/upload/
    
    Accepts multipart/form-data with 'video' file (max 2GB).
    """
    serializer_class   = ShortVideoCreateSerializer
    permission_classes = [IsAuthenticated]
    parser_classes     = [MultiPartParser, FormParser]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            instance = self.perform_create(serializer)
        except Exception as exc:
            # Catch and return clean error messages (especially for large files)
            if "too large" in str(exc).lower() or "2gb" in str(exc).lower():
                return Response(
                    {"video": ["Video file is too large. Maximum allowed size is 2 GB."]},
                    status=status.HTTP_400_BAD_REQUEST
                )
            raise  # Re-raise other unexpected errors

        read_serializer = ShortVideoSerializer(
            instance, context={'request': request}
        )
        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        # Frontend sends the file as 'file', not 'video'
        video_file = self.request.FILES.get('file') or self.request.FILES.get('video')

        # Frontend sends league_id; resolve it to a League instance
        league = None
        league_id = self.request.data.get('league_id') or self.request.data.get('league')
        if league_id:
            from leagues.models import League
            try:
                league = League.objects.get(pk=league_id)
            except League.DoesNotExist:
                pass

        duration = 0
        tmp_path = None
        compressed_path = None

        try:
            if video_file:
                # 1. Save original to temp
                with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp:
                    for chunk in video_file.chunks():
                        tmp.write(chunk)
                    tmp_path = tmp.name

                # 2. Compress
                compressed_path = tmp_path + '_compressed.mp4'
                compress_video(tmp_path, compressed_path)

                duration = extract_duration(compressed_path)

                # 3. Keep the file open while Django/GCS streams it
                f = open(compressed_path, 'rb')
                try:
                    django_file = File(f, name=video_file.name)
                    instance = serializer.save(
                        author=self.request.user,
                        duration=duration,
                        video=django_file,
                        league=league,
                    )
                finally:
                    f.close()

                # 4. Thumbnail
                if compressed_path and not instance.thumbnail:
                    try:
                        thumb_bytes = generate_thumbnail(compressed_path)
                        instance.thumbnail.save(
                            f'thumb_{instance.pk}.jpg',
                            ContentFile(thumb_bytes),
                            save=True,
                        )
                    except Exception:
                        pass

            else:
                instance = serializer.save(
                    author=self.request.user,
                    duration=duration,
                    league=league,
                )

            return instance

        finally:
            for path in (tmp_path, compressed_path):
                if path and os.path.exists(path):
                    try:
                        os.unlink(path)
                    except Exception:
                        pass        
    # ─────────────────────────────────────────────────────────────────────────────
# FEED
# ─────────────────────────────────────────────────────────────────────────────

class ShortVideoPagination(LimitOffsetPagination):
    default_limit = 10
    max_limit     = 20


class ShortVideoFeedView(ListAPIView):
    """
    GET /api/videos/shorts/feed/
    """
    authentication_classes = [TokenAuthentication]
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

    def list(self, request, *args, **kwargs):
        qs   = self.get_queryset()
        page = self.paginate_queryset(list(qs))

        serializer = self.get_serializer(
            page if page is not None else qs,
            many=True,
            context={'request': request},
        )

        if page is not None:
            return self.get_paginated_response(serializer.data)

        return Response({
            'results': serializer.data,
            'count':   len(serializer.data),
        })


# ─────────────────────────────────────────────────────────────────────────────
# STREAMING
# ─────────────────────────────────────────────────────────────────────────────

class ShortVideoStreamView(APIView):
    """
    GET /api/videos/shorts/<pk>/stream/
    GET /api/videos/shorts/<pk>/stream/?token=<drf_token>
    """
    authentication_classes = [TokenAuthentication]
    permission_classes     = []

    def get(self, request, pk):
        user = request.user

        if not user or not user.is_authenticated:
            token_key = request.query_params.get('token', '').strip()
            if token_key:
                try:
                    token_obj = Token.objects.select_related('user').get(key=token_key)
                    user = token_obj.user
                except Token.DoesNotExist:
                    return Response(
                        {'detail': 'Invalid or expired token.'},
                        status=status.HTTP_401_UNAUTHORIZED,
                    )

        if not user or not user.is_authenticated:
            return Response(
                {'detail': 'Authentication credentials were not provided.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        video = get_object_or_404(ShortVideo, pk=pk)
        return stream_video_response(request, video)


# ─────────────────────────────────────────────────────────────────────────────
# ENGAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

class VideoLikeToggleView(APIView):
    """POST /like/ and DELETE /like/"""
    authentication_classes = [TokenAuthentication]
    permission_classes     = [IsAuthenticated]

    def post(self, request, pk):
        video = get_object_or_404(ShortVideo, pk=pk)
        like, created = VideoLike.objects.get_or_create(user=request.user, video=video)

        if created:
            video.refresh_from_db(fields=['cached_likes'])
            return Response(
                {'liked': True, 'likes_count': video.cached_likes},
                status=status.HTTP_201_CREATED,
            )

        like.delete()
        video.refresh_from_db(fields=['cached_likes'])
        return Response(
            {'liked': False, 'likes_count': video.cached_likes},
            status=status.HTTP_200_OK,
        )

    def delete(self, request, pk):
        """FIX-3: Returns 200 with body"""
        video = get_object_or_404(ShortVideo, pk=pk)
        deleted, _ = VideoLike.objects.filter(user=request.user, video=video).delete()
        video.refresh_from_db(fields=['cached_likes'])

        if deleted:
            return Response(
                {'liked': False, 'likes_count': video.cached_likes},
                status=status.HTTP_200_OK,
            )
        return Response({'detail': 'Not liked.'}, status=status.HTTP_404_NOT_FOUND)


class VideoViewRecordView(APIView):
    """POST /view/"""
    authentication_classes = [TokenAuthentication]
    permission_classes     = [IsAuthenticated]

    def post(self, request, pk):
        video = get_object_or_404(ShortVideo, pk=pk)
        serializer = VideoViewSerializer(
            data={**request.data, 'video': str(video.pk)}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class VideoShareRecordView(APIView):
    """POST /share/"""
    authentication_classes = [TokenAuthentication]
    permission_classes     = [IsAuthenticated]

    def post(self, request, pk):
        video = get_object_or_404(ShortVideo, pk=pk)
        serializer = VideoShareSerializer(
            data={**request.data, 'video': str(video.pk)}
        )
        serializer.is_valid(raise_exception=True)
        share = serializer.save(user=request.user)

        platform = share.platform
        payload = {
            **serializer.data,
            'share_url':      video.share_url,
            'og_title':       video.og_title,
            'og_description': video.og_description,
            'thumbnail_url': (
                request.build_absolute_uri(video.thumbnail.url)
                if video.thumbnail else None
            ),
        }

        if platform == 'whatsapp':
            text = build_whatsapp_share_text(video)
            payload['text'] = text
            payload['whatsapp_url'] = f"https://wa.me/?text={quote(text)}"

        elif platform == 'telegram':
            text = build_telegram_share_text(video)
            payload['text'] = text
            payload['telegram_url'] = (
                f"https://t.me/share/url"
                f"?url={quote(video.share_url, safe='')}"
                f"&text={quote(video.og_title, safe='')}"
            )

        elif platform == 'twitter':
            payload['twitter_url'] = (
                f"https://twitter.com/intent/tweet"
                f"?url={quote(video.share_url, safe='')}"
                f"&text={quote(video.og_title, safe='')}"
            )

        else:
            payload['share_text'] = video.share_url

        return Response(payload, status=status.HTTP_201_CREATED)


class VideoReshareView(APIView):
    """POST /reshare/"""
    authentication_classes = [TokenAuthentication]
    permission_classes     = [IsAuthenticated]

    RESHARE_PLATFORM = 'reshare'

    def post(self, request, pk):
        video = get_object_or_404(ShortVideo, pk=pk)

        existing = VideoShare.objects.filter(
            user=request.user,
            video=video,
            platform=self.RESHARE_PLATFORM,
        ).first()

        if existing:
            existing.delete()
            return Response({'reshared': False}, status=status.HTTP_200_OK)

        VideoShare.objects.create(
            user=request.user,
            video=video,
            platform=self.RESHARE_PLATFORM,
        )
        return Response({'reshared': True}, status=status.HTTP_201_CREATED)


# ─────────────────────────────────────────────────────────────────────────────
# COMMENTS
# ─────────────────────────────────────────────────────────────────────────────

class VideoCommentListCreateView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes     = [IsAuthenticatedOrReadOnly]

    def get(self, request, pk):
        video = get_object_or_404(ShortVideo, pk=pk)
        comments = (
            VideoComment.objects
            .filter(video=video, parent__isnull=True)
            .select_related('author', 'author__profile')
            .prefetch_related('mentions__user', 'replies')
            .order_by('created_at')
        )
        serializer = VideoCommentSerializer(
            comments, many=True, context={'request': request}
        )
        return Response(serializer.data)

    def post(self, request, pk):
        video = get_object_or_404(ShortVideo, pk=pk)
        serializer = VideoCommentCreateSerializer(
            data={**request.data, 'video': str(video.pk)},
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        comment = serializer.save(author=request.user)

        read_serializer = VideoCommentSerializer(
            comment, context={'request': request}
        )
        return Response(read_serializer.data, status=status.HTTP_201_CREATED)


class CommentRepliesListView(ListAPIView):
    authentication_classes = [TokenAuthentication]
    permission_classes     = [IsAuthenticatedOrReadOnly]
    serializer_class       = VideoCommentSerializer

    def get_queryset(self):
        video_pk   = self.kwargs['pk']
        comment_pk = self.kwargs['comment_pk']
        return (
            VideoComment.objects
            .filter(video_id=video_pk, parent_id=comment_pk)
            .select_related('author', 'author__profile')
            .prefetch_related('mentions__user')
            .order_by('created_at')
        )


class CommentDetailView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes     = [IsAuthenticated]

    def _get_own_comment(self, request, pk):
        comment = get_object_or_404(VideoComment, pk=pk)
        if comment.author_id != request.user.pk:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You can only edit or delete your own comments.")
        return comment

    def patch(self, request, pk):
        comment = self._get_own_comment(request, pk)
        serializer = VideoCommentCreateSerializer(
            comment, data=request.data, partial=True,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        # You can set is_edited=True here if desired via signal
        read_serializer = VideoCommentSerializer(updated, context={'request': request})
        return Response(read_serializer.data)

    def delete(self, request, pk):
        comment = self._get_own_comment(request, pk)
        comment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)