"""
ConnectDial — Short Video Feed Algorithm
========================================

This version uses the denormalized `cached_avg_watch_ratio` field for high performance.
No expensive GROUP BY / Avg() queries in the hot feed path.

Scoring formula:
    score = 
        watch_ratio    * 4.0   (strongest quality signal)
      + likes_count    * 2.0
      + comments_count * 3.0
      + shares_count   * 5.0   (highest weight)
      - age_penalty
      + interest_boost (explicit follows + watch history)
"""

from django.db.models import (
    F, ExpressionWrapper, FloatField, Case, When, Value, IntegerField
)
from django.utils import timezone
from django.core.cache import cache

from .models import ShortVideo


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

CACHE_TTL          = 60 * 5          # 5 minutes
AGE_DECAY_PER_HOUR = 0.3
AGE_DECAY_CAP_HRS  = 24.0
HISTORY_LIMIT      = 10
FEED_FETCH_SIZE    = 200             # Used by ShortVideoFeedView

# Engagement weights
W_WATCH_RATIO = 4.0
W_LIKES       = 2.0
W_COMMENTS    = 3.0
W_SHARES      = 5.0

# Personalisation weights
W_EXP_LEAGUE  = 2.0
W_EXP_TEAM    = 3.0
W_HIST_LEAGUE = 1.0
W_HIST_TEAM   = 1.5


# ─────────────────────────────────────────────────────────────────────────────
# CACHE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _cache_key(user_id: int) -> str:
    return f"short_feed:v4:{user_id}"


def bust_feed_cache(user_id: int) -> None:
    """Bust feed cache for a specific user."""
    cache.delete(_cache_key(user_id))


def _preserve_order_list(ids: list) -> list:
    """Rehydrate videos while preserving the original scored order."""
    if not ids:
        return []

    import uuid as _uuid
    uuid_ids = [_uuid.UUID(i) for i in ids]

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
            views_count=F('cached_views'),
            order=order_expr,
        )
        .order_by('order')
    )


# ─────────────────────────────────────────────────────────────────────────────
# USER INTEREST HELPERS (Cached where possible)
# ─────────────────────────────────────────────────────────────────────────────

def _user_interest_leagues(user):
    if hasattr(user, 'favorite_league_id') and user.favorite_league_id:
        return [user.favorite_league_id]
    return []


def _user_interest_teams(user):
    if hasattr(user, 'favorite_team_id') and user.favorite_team_id:
        return [user.favorite_team_id]
    return []


def _user_history_leagues(user, limit=HISTORY_LIMIT):
    from .models import VideoView
    return list(
        VideoView.objects
        .filter(user=user, video__league__isnull=False)
        .values_list('video__league_id', flat=True)
        .order_by('-created_at')
        .distinct()[:limit]
    )


def _user_history_teams(user, limit=HISTORY_LIMIT):
    from .models import VideoView
    return list(
        VideoView.objects
        .filter(user=user, video__team__isnull=False)
        .values_list('video__team_id', flat=True)
        .order_by('-created_at')
        .distinct()[:limit]
    )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN FEED FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def get_short_video_feed(user, bypass_cache: bool = False) -> list:
    """
    Returns a list of up to FEED_FETCH_SIZE scored ShortVideo objects.
    Uses cached_avg_watch_ratio for performance.
    """
    cache_key = _cache_key(user.pk)

    # Cache hit path
    if not bypass_cache:
        cached_ids = cache.get(cache_key)
        if cached_ids:
            return _preserve_order_list(cached_ids)

    now = timezone.now()

    # ── User interests ─────────────────────────────────────────────────────
    explicit_leagues = _user_interest_leagues(user)
    explicit_teams   = _user_interest_teams(user)
    history_leagues  = _user_history_leagues(user)
    history_teams    = _user_history_teams(user)

    # ── Base queryset ─────────────────────────────────────────────────────
    qs = ShortVideo.objects.filter(status='published').select_related(
        'author', 'author__profile', 'league', 'team'
    ).prefetch_related('likes')

    # ── Annotations ───────────────────────────────────────────────────────
    qs = qs.annotate(
        likes_count=F('cached_likes'),
        comments_count=F('cached_comments'),
        shares_count=F('cached_shares'),
        views_count=F('cached_views'),
        # Use pre-computed ratio from signals.py (very fast)
        watch_ratio=F('cached_avg_watch_ratio'),
    )

    # Age calculation (in hours)
    qs = qs.annotate(
        age_hours=ExpressionWrapper(
            Extract(now - F('created_at'), 'epoch') / 3600.0,
            output_field=FloatField(),
        )
    )

    qs = qs.annotate(
        age_hours_capped=Case(
            When(age_hours__gt=AGE_DECAY_CAP_HRS, then=Value(AGE_DECAY_CAP_HRS)),
            default=F('age_hours'),
            output_field=FloatField(),
        )
    )

    # Personalisation boosts
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
        interest_boost=ExpressionWrapper(
            F('explicit_league_boost') + F('explicit_team_boost') +
            F('history_league_boost') + F('history_team_boost'),
            output_field=FloatField(),
        )
    )

    # Final score
    qs = qs.annotate(
        score=ExpressionWrapper(
            F('watch_ratio')    * W_WATCH_RATIO +
            F('likes_count')    * W_LIKES       +
            F('comments_count') * W_COMMENTS    +
            F('shares_count')   * W_SHARES      +
            F('age_hours_capped') * -AGE_DECAY_PER_HOUR +
            F('interest_boost'),
            output_field=FloatField(),
        )
    ).order_by('-score')

    # Evaluate once and cache
    result = list(qs[:FEED_FETCH_SIZE])

    # Cache only the IDs (lightweight)
    ids = [str(v.id) for v in result]
    cache.set(cache_key, ids, CACHE_TTL)

    return result