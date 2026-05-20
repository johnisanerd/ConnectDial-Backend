"""
ConnectDial — Short Video Feed Algorithm (Stable Version)
"""

from django.db.models import (
    F, ExpressionWrapper, FloatField, Case, When, Value, IntegerField
)
from django.db.models.functions import ExtractEpoch
from django.utils import timezone
from django.core.cache import cache

from .models import ShortVideo, VideoView


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
CACHE_TTL          = 60 * 5
AGE_DECAY_PER_HOUR = 0.3
AGE_DECAY_CAP_HRS  = 24.0
HISTORY_LIMIT      = 10
FEED_FETCH_SIZE    = 200

W_WATCH_RATIO = 4.0
W_LIKES       = 2.0
W_COMMENTS    = 3.0
W_SHARES      = 5.0

W_EXP_LEAGUE  = 2.0
W_EXP_TEAM    = 3.0
W_HIST_LEAGUE = 1.0
W_HIST_TEAM   = 1.5


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _cache_key(user_id: int) -> str:
    return f"short_feed:v4:{user_id}"


def bust_feed_cache(user_id: int) -> None:
    cache.delete(_cache_key(user_id))


def _user_interest_leagues(user):
    return [user.favorite_league_id] if getattr(user, 'favorite_league_id', None) else []


def _user_interest_teams(user):
    return [user.favorite_team_id] if getattr(user, 'favorite_team_id', None) else []


def _user_history_leagues(user, limit=HISTORY_LIMIT):
    """Safe history fetch"""
    try:
        return list(
            VideoView.objects
            .filter(user=user, video__league__isnull=False)
            .values_list('video__league_id', flat=True)
            .order_by('-created_at')
            .distinct()[:limit]
        )
    except Exception:
        return []


def _user_history_teams(user, limit=HISTORY_LIMIT):
    """Safe history fetch"""
    try:
        return list(
            VideoView.objects
            .filter(user=user, video__team__isnull=False)
            .values_list('video__team_id', flat=True)
            .order_by('-created_at')
            .distinct()[:limit]
        )
    except Exception:
        return []


def _preserve_order_list(ids: list):
    if not ids:
        return []

    from uuid import UUID
    uuid_ids = [UUID(i) for i in ids]

    order_expr = Case(
        *[When(pk=pk, then=Value(i)) for i, pk in enumerate(uuid_ids)],
        output_field=IntegerField(),
    )

    return list(
        ShortVideo.objects
        .filter(pk__in=uuid_ids, status='published')
        .select_related('author', 'author__profile', 'league', 'team')
        .prefetch_related('likes')
        .annotate(
            likes_count=F('cached_likes'),
            comments_count=F('cached_comments'),
            shares_count=F('cached_shares'),
            order=order_expr,
        )
        .order_by('order')
    )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN FEED
# ─────────────────────────────────────────────────────────────────────────────
def get_short_video_feed(user, bypass_cache: bool = False):
    """Returns ordered list of ShortVideo objects"""
    try:
        cache_key = _cache_key(user.pk)

        if not bypass_cache:
            cached_ids = cache.get(cache_key)
            if cached_ids:
                return _preserve_order_list(cached_ids)

        # User interests
        explicit_leagues = _user_interest_leagues(user)
        explicit_teams   = _user_interest_teams(user)
        history_leagues  = _user_history_leagues(user)
        history_teams    = _user_history_teams(user)

        # Base queryset
        qs = ShortVideo.objects.filter(status='published').select_related(
            'author', 'author__profile', 'league', 'team'
        )

        # Annotations
        qs = qs.annotate(
            likes_count=F('cached_likes'),
            comments_count=F('cached_comments'),
            shares_count=F('cached_shares'),
            watch_ratio=F('cached_avg_watch_ratio'),
            age_hours=ExpressionWrapper(
                ExtractEpoch(timezone.now() - F('created_at')) / 3600.0,
                output_field=FloatField(),
            ),
        )

        qs = qs.annotate(
            age_hours_capped=Case(
                When(age_hours__gt=AGE_DECAY_CAP_HRS, then=Value(AGE_DECAY_CAP_HRS)),
                default=F('age_hours'),
                output_field=FloatField(),
            )
        )

        # Interest boosts
        qs = qs.annotate(
            explicit_league_boost=Case(
                When(league_id__in=explicit_leagues, then=Value(W_EXP_LEAGUE)),
                default=Value(0.0),
                output_field=FloatField(),
            ),
            explicit_team_boost=Case(
                When(team_id__in=explicit_teams, then=Value(W_EXP_TEAM)),
                default=Value(0.0),
                output_field=FloatField(),
            ),
            history_league_boost=Case(
                When(league_id__in=history_leagues, then=Value(W_HIST_LEAGUE)),
                default=Value(0.0),
                output_field=FloatField(),
            ),
            history_team_boost=Case(
                When(team_id__in=history_teams, then=Value(W_HIST_TEAM)),
                default=Value(0.0),
                output_field=FloatField(),
            ),
        )

        qs = qs.annotate(
            interest_boost=F('explicit_league_boost') + F('explicit_team_boost') +
                          F('history_league_boost') + F('history_team_boost')
        )

        # Final score
        qs = qs.annotate(
            score=ExpressionWrapper(
                F('watch_ratio') * W_WATCH_RATIO +
                F('likes_count') * W_LIKES +
                F('comments_count') * W_COMMENTS +
                F('shares_count') * W_SHARES +
                F('age_hours_capped') * (-AGE_DECAY_PER_HOUR) +
                F('interest_boost'),
                output_field=FloatField(),
            )
        ).order_by('-score')

        result = list(qs[:FEED_FETCH_SIZE])

        # Cache IDs
        cache.set(cache_key, [str(v.id) for v in result], CACHE_TTL)

        return result

    except Exception as e:
        # ← Very important for debugging
        print(f"[FEED ERROR] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        
        # Return something safe so app doesn't break completely
        return list(ShortVideo.objects.filter(status='published')[:30])vide