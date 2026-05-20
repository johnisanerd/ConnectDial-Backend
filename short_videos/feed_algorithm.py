"""
ConnectDial — Short Video Feed Algorithm (Fixed)
"""

from django.db.models import (
    F, ExpressionWrapper, FloatField, Case, When, Value, IntegerField,
    Q
)
from django.utils import timezone
from django.core.cache import cache
from django.db.models.functions import ExtractEpoch   # ← Correct import

from .models import ShortVideo
from django.db.models.functions import ExtractEpoch

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG (unchanged)
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
# CACHE & HELPERS (unchanged)
# ─────────────────────────────────────────────────────────────────────────────
def _user_interest_leagues(user):
    if getattr(user, 'favorite_league_id', None):
        return [user.favorite_league_id]
    return []

def _user_interest_teams(user):
    if getattr(user, 'favorite_team_id', None):
        return [user.favorite_team_id]
    return []
def _cache_key(user_id: int) -> str:
    return f"short_feed:v4:{user_id}"


def bust_feed_cache(user_id: int) -> None:
    cache.delete(_cache_key(user_id))


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
            views_count=F('cached_views'),
            order=order_expr,
        )
        .order_by('order')
    )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN FEED (FIXED)
# ─────────────────────────────────────────────────────────────────────────────

def get_short_video_feed(user, bypass_cache: bool = False):
    cache_key = _cache_key(user.pk)

    if not bypass_cache:
        cached_ids = cache.get(cache_key)
        if cached_ids:
            return _preserve_order_list(cached_ids)

    now = timezone.now()

    # User interests
    explicit_leagues = _user_interest_leagues(user)
    explicit_teams   = _user_interest_teams(user)
    history_leagues  = _user_history_leagues(user)
    history_teams    = _user_history_teams(user)

    # Base queryset
    qs = ShortVideo.objects.filter(status='published').select_related(
        'author', 'author__profile', 'league', 'team'
    ).prefetch_related('likes')

    # Annotations
    qs = qs.annotate(
        likes_count=F('cached_likes'),
        comments_count=F('cached_comments'),
        shares_count=F('cached_shares'),
        views_count=F('cached_views'),
        watch_ratio=F('cached_avg_watch_ratio'),
    )

    # === FIXED AGE CALCULATION ===
    qs = qs.annotate(
        age_hours=ExpressionWrapper(
            ExtractEpoch(now - F('created_at')) / 3600.0,
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
            F('age_hours_capped') * (-AGE_DECAY_PER_HOUR) +
            F('interest_boost'),
            output_field=FloatField(),
        )
    ).order_by('-score')

    # Materialize + cache
    result = list(qs[:FEED_FETCH_SIZE])

    ids = [str(v.id) for v in result]
    cache.set(cache_key, ids, CACHE_TTL)

    return result