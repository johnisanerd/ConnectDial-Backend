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
    extract_duration,
    generate_thumbnail,
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
            status='draft',
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
                target=self._save_raw_and_publish_fast,
                args=(instance,),
                daemon=True,
            )

            t.start()

        return instance

    def _save_raw_and_publish_fast(self, instance):

        try:

            if not instance.video:
                return

            video_path = instance.video.path

            # ─────────────────────────────────────────
            # DURATION
            # ─────────────────────────────────────────

            try:
                duration = extract_duration(video_path)

            except Exception:
                duration = 0

            instance.duration = duration

            update_fields = ['duration']

            # ─────────────────────────────────────────
            # THUMBNAIL
            # ─────────────────────────────────────────

            try:

                thumb_bytes = generate_thumbnail(video_path)

                instance.thumbnail.save(
                    f'thumb_{instance.pk}.jpg',
                    ContentFile(thumb_bytes),
                    save=False,
                )

                update_fields.append('thumbnail')

            except Exception:
                pass

            # ─────────────────────────────────────────
            # PUBLISH
            # ─────────────────────────────────────────

            instance.status = 'published'

            update_fields.append('status')

            instance.save(update_fields=update_fields)

        except Exception:

            try:

                instance.status = 'published'

                instance.save(update_fields=['status'])

            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# FEED
# ─────────────────────────────────────────────────────────────────────────────

class ShortVideoPagination(LimitOffsetPagination):

    default_limit = 10

    max_limit = 20


class ShortVideoFeedView(ListAPIView):

    authentication_classes = [
        TokenAuthentication,
        SessionAuthentication
    ]

    permission_classes = [IsAuthenticatedOrReadOnly]

    serializer_class = ShortVideoSerializer

    pagination_class = ShortVideoPagination

    def get_queryset(self):
        """
        Fetches personalized ranked feeds using your advanced ranking engine
        when authenticated, falling back to a clean chronological list for guests.
        """

        user = self.request.user

        if user and user.is_authenticated:

            from .feed_algorithm import get_short_video_feed

            return get_short_video_feed(user)

        return (
            ShortVideo.objects
            .filter(status='published')
            .select_related(
                'author',
                'author__profile',
                'league',
                'team'
            )
            .prefetch_related(
                'author__fan_preferences',
                'author__fan_preferences__team'
            )
            .order_by('-created_at')
        )

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

            ShortVideo.objects.filter(pk=pk).update(
                cached_likes=F('cached_likes') - 1
            )

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

        ShortVideo.objects.filter(pk=pk).update(
            cached_likes=F('cached_likes') + 1
        )

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

class VideoCommentListCreateView(APIView):
    """
    GET  /api/videos/shorts/<pk>/comments/ -> Fetch optimized top-level comments
    POST /api/videos/shorts/<pk>/comments/ -> Post clean comment
    """
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes     = [IsAuthenticatedOrReadOnly]

    def get(self, request, pk):
        video = get_object_or_404(ShortVideo, pk=pk)
        
        qs = (
            VideoComment.objects
            .filter(video=video, parent__isnull=True)
            .select_related('author', 'author__profile', 'video__league')
            .prefetch_related('author__fan_preferences', 'author__fan_preferences__team', 'replies')
            .order_by('-created_at')
        )

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
        ShortVideo.objects.filter(pk=pk).update(cached_comments=F('cached_comments') + 1)

        return Response(
            VideoCommentSerializer(comment, context={'request': request}).data,
            status=status.HTTP_201_CREATED
        )


class CommentRepliesListView(ListAPIView):
    """
    GET /api/videos/shorts/<pk>/comments/<comment_pk>/replies/ -> Optimized sub-threads
    """
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
            .select_related('author', 'author__profile', 'video__league')
            .prefetch_related('author__fan_preferences', 'author__fan_preferences__team')
            .order_by('created_at')
        )
        
    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['request'] = self.request
        return ctx


class CommentDetailView(APIView):
    """
    PATCH  /api/videos/comments/<pk>/ -> Safe patch comment edits
    DELETE /api/videos/comments/<pk>/ -> Atomic removal
    """
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes     = [IsAuthenticated]

    def _get_own_comment(self, request, pk):
        comment = get_object_or_404(VideoComment, pk=pk)
        if comment.author_id != request.user.id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You do not own modification privileges on this resource.")
        return comment

    def patch(self, request, pk):
        comment = self._get_own_comment(request, pk)
        data = _request_data_as_dict(request.data)
        data.pop('video', None)

        serializer = VideoCommentCreateSerializer(
            comment,
            data=data,
            partial=True,
            context={'request': request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        updated = serializer.save(is_edited=True)
        return Response(
            VideoCommentSerializer(updated, context={'request': request}).data,
            status=status.HTTP_200_OK
        )

    def delete(self, request, pk):
        comment = self._get_own_comment(request, pk)
        video_pk = comment.video_id
        
        comment.delete()
        ShortVideo.objects.filter(pk=video_pk).update(cached_comments=F('cached_comments') - 1)
        return Response(status=status.HTTP_204_NO_CONTENT)