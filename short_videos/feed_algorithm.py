"""
ConnectDial — Short Video Feed Algorithm
- Accepts an optional league_id / team_id to hard-filter before scoring
- Age decay uses EPOCH via RawSQL so it works on any Django+PostgreSQL version
- Safe fallback when any DB annotation fails
"""

from django.db.models import (
    F, ExpressionWrapper, FloatField, Case, When, Value, IntegerField
)
from django.db.models.expressions import RawSQL
from django.utils import timezone
from django.core.cache import cache

from .models import ShortVideo, VideoView


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
CACHE_TTL          = 60 * 5        # 5 min
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
# CACHE KEY
# Includes league/team so filtered feeds get their own cache slot.
# ─────────────────────────────────────────────────────────────────────────────
def _cache_key(user_id, league_id=None, team_id=None) -> str:
    suffix = f":l{league_id}" if league_id else ""
    suffix += f":t{team_id}"  if team_id  else ""
    return f"short_feed:v5:{user_id}{suffix}"


def bust_feed_cache(user_id: int) -> None:
    """Bust the unfiltered feed cache for a user (post-publish signal)."""
    cache.delete(_cache_key(user_id))


# ─────────────────────────────────────────────────────────────────────────────
# USER INTEREST HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _user_interest_leagues(user):
    return [user.favorite_league_id] if getattr(user, 'favorite_league_id', None) else []


def _user_interest_teams(user):
    return [user.favorite_team_id] if getattr(user, 'favorite_team_id', None) else []


def _user_history_leagues(user, limit=HISTORY_LIMIT):
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


# ─────────────────────────────────────────────────────────────────────────────
# RE-HYDRATE ORDERED LIST FROM CACHED IDs
# ─────────────────────────────────────────────────────────────────────────────
def _preserve_order_list(ids: list):
    if not ids:
        return []

    from uuid import UUID
    try:
        uuid_ids = [UUID(i) for i in ids]
    except Exception:
        return []

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
# MAIN FEED FUNCTION
# ─────────────────────────────────────────────────────────────────────────────
def get_short_video_feed(user, league_id=None, team_id=None, bypass_cache: bool = False):
    """
    Returns an ordered list of ShortVideo objects.

    Parameters
    ----------
    user        : authenticated User instance
    league_id   : optional str/int – hard-filter to a specific league
    team_id     : optional str/int – hard-filter to a specific team
    bypass_cache: skip reading from cache (always re-scores)
    """
    try:
        cache_key = _cache_key(user.pk, league_id=league_id, team_id=team_id)

        if not bypass_cache:
            cached_ids = cache.get(cache_key)
            if cached_ids:
                return _preserve_order_list(cached_ids)

        # ── Base queryset ─────────────────────────────────────────────────────
        qs = ShortVideo.objects.filter(status='published').select_related(
            'author', 'author__profile', 'league', 'team'
        )

        # ── Hard league / team filter (from UI chip or route param) ───────────
        if league_id:
            qs = qs.filter(league_id=league_id)

        if team_id:
            qs = qs.filter(team_id=team_id)

        # ── User interest signals ─────────────────────────────────────────────
        explicit_leagues = _user_interest_leagues(user)
        explicit_teams   = _user_interest_teams(user)
        history_leagues  = _user_history_leagues(user)
        history_teams    = _user_history_teams(user)

        # ── Annotations ───────────────────────────────────────────────────────
        # Age in hours using raw EPOCH subtraction — works on PostgreSQL without
        # needing ExtractEpoch (which requires Django 4.x+ or extra imports).
        qs = qs.annotate(
            likes_count=F('cached_likes'),
            comments_count=F('cached_comments'),
            shares_count=F('cached_shares'),
            watch_ratio=F('cached_avg_watch_ratio'),
            # EPOCH diff → seconds → hours  (RawSQL is DB-level, very fast)
            age_hours=ExpressionWrapper(
                RawSQL(
                    "EXTRACT(EPOCH FROM (NOW() - created_at)) / 3600.0",
                    []
                ),
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

        # ── Interest boosts ───────────────────────────────────────────────────
        # Only apply boosts when we're NOT already hard-filtering to that league/team
        # (no point boosting something the filter already guarantees).
        qs = qs.annotate(
            explicit_league_boost=Case(
                When(league_id__in=explicit_leagues, then=Value(W_EXP_LEAGUE))
                if explicit_leagues and not league_id else
                When(pk__isnull=True, then=Value(0.0)),   # never-true sentinel
                default=Value(0.0),
                output_field=FloatField(),
            ),
            explicit_team_boost=Case(
                When(team_id__in=explicit_teams, then=Value(W_EXP_TEAM))
                if explicit_teams and not team_id else
                When(pk__isnull=True, then=Value(0.0)),
                default=Value(0.0),
                output_field=FloatField(),
            ),
            history_league_boost=Case(
                When(league_id__in=history_leagues, then=Value(W_HIST_LEAGUE))
                if history_leagues and not league_id else
                When(pk__isnull=True, then=Value(0.0)),
                default=Value(0.0),
                output_field=FloatField(),
            ),
            history_team_boost=Case(
                When(team_id__in=history_teams, then=Value(W_HIST_TEAM))
                if history_teams and not team_id else
                When(pk__isnull=True, then=Value(0.0)),
                default=Value(0.0),
                output_field=FloatField(),
            ),
        )

        qs = qs.annotate(
            interest_boost=(
                F('explicit_league_boost') +
                F('explicit_team_boost') +
                F('history_league_boost') +
                F('history_team_boost')
            )
        )

        # ── Final score ───────────────────────────────────────────────────────
        qs = qs.annotate(
            score=ExpressionWrapper(
                F('watch_ratio')    * W_WATCH_RATIO +
                F('likes_count')    * W_LIKES +
                F('comments_count') * W_COMMENTS +
                F('shares_count')   * W_SHARES +
                F('age_hours_capped') * (-AGE_DECAY_PER_HOUR) +
                F('interest_boost'),
                output_field=FloatField(),
            )
        ).order_by('-score')

        result = list(qs[:FEED_FETCH_SIZE])

        cache.set(cache_key, [str(v.id) for v in result], CACHE_TTL)

        return result

    except Exception as e:
        import traceback
        print(f"[FEED ERROR] {type(e).__name__}: {e}")
        traceback.print_exc()

        # ── Safe fallback (chronological, respects hard filter) ───────────────
        fallback = ShortVideo.objects.filter(status='published')
        if league_id:
            fallback = fallback.filter(league_id=league_id)
        if team_id:
            fallback = fallback.filter(team_id=team_id)
        return list(fallback.order_by('-created_at')[:30])