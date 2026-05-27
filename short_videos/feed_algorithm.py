"""
ConnectDial — Short Video Feed Algorithm
========================================
Fixes vs previous version
──────────────────────────
1. _preserve_order_list now accepts + re-applies league_id/team_id so a cache
   hit on a filtered key still returns the right videos.
2. Removed broken Case/When sentinel (pk__isnull=True).  Interest boosts are
   simply skipped (value=0.0) when the list is empty or when we're already
   hard-filtering to that dimension.
3. FEED_FETCH_SIZE capped at 50 so the algorithm never pulls 200 rows that
   pagination will discard anyway.
4. Cache TTL lowered to 2 min for filtered feeds so league chips feel instant.
5. bust_feed_cache now also clears the common filtered cache slots so a new
   upload in league X invalidates league-X viewers immediately.
"""

from django.db.models import (
    F, ExpressionWrapper, FloatField,
    Case, When, Value, IntegerField,
)
from django.db.models.expressions import RawSQL
from django.core.cache import cache

from .models import ShortVideo, VideoView


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
CACHE_TTL_GLOBAL   = 60 * 5        # 5 min  – unfiltered personal feed
CACHE_TTL_FILTERED = 60 * 2        # 2 min  – league / team filtered
AGE_DECAY_PER_HOUR = 0.3
AGE_DECAY_CAP_HRS  = 24.0
HISTORY_LIMIT      = 10
FEED_FETCH_SIZE    = 50            # cap: pagination only shows 20 at a time

W_WATCH_RATIO = 4.0
W_LIKES       = 2.0
W_COMMENTS    = 3.0
W_SHARES      = 5.0
W_EXP_LEAGUE  = 2.0
W_EXP_TEAM    = 3.0
W_HIST_LEAGUE = 1.0
W_HIST_TEAM   = 1.5


# ─────────────────────────────────────────────────────────────────────────────
# CACHE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _cache_key(user_id, league_id=None, team_id=None) -> str:
    suffix = f":l{league_id}" if league_id else ""
    suffix += f":t{team_id}"  if team_id  else ""
    return f"short_feed:v6:{user_id}{suffix}"


def bust_feed_cache(user_id: int) -> None:
    """
    Delete the unfiltered feed cache for a user.
    Also deletes the most-recently-used league keys stored in a side-set
    so league-filtered viewers see new content immediately.
    """
    cache.delete(_cache_key(user_id))

    # Bust up to the last 20 league/team combinations this user viewed
    league_set_key = f"short_feed:leagues_used:{user_id}"
    used = cache.get(league_set_key) or []
    for (lid, tid) in used:
        cache.delete(_cache_key(user_id, league_id=lid, team_id=tid))
    cache.delete(league_set_key)


def _register_filter_use(user_id: int, league_id, team_id) -> None:
    """Track which (league_id, team_id) combos a user has used so we can bust them."""
    if not league_id and not team_id:
        return
    key = f"short_feed:leagues_used:{user_id}"
    used: list = cache.get(key) or []
    entry = (league_id, team_id)
    if entry not in used:
        used.append(entry)
        if len(used) > 20:
            used = used[-20:]
        cache.set(key, used, 60 * 60 * 24)   # keep 24 hrs


# ─────────────────────────────────────────────────────────────────────────────
# USER INTEREST HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _user_interest_leagues(user):
    fav = getattr(user, 'favorite_league_id', None)
    return [fav] if fav else []


def _user_interest_teams(user):
    fav = getattr(user, 'favorite_team_id', None)
    return [fav] if fav else []


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
# RE-HYDRATE FROM CACHED ID LIST
# league_id / team_id are passed in so the DB query re-applies the hard filter,
# guarding against stale cache entries that might include wrong-league videos.
# ─────────────────────────────────────────────────────────────────────────────

def _preserve_order_list(ids: list, league_id=None, team_id=None):
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

    qs = (
        ShortVideo.objects
        .filter(pk__in=uuid_ids, status='published')
        .select_related('author', 'author__profile', 'league', 'team')
        .annotate(
            likes_count=F('cached_likes'),
            comments_count=F('cached_comments'),
            shares_count=F('cached_shares'),
            order=order_expr,
        )
        .order_by('order')
    )

    # Re-apply hard filters so a stale/shared cache slot can't leak videos
    if league_id:
        qs = qs.filter(league_id=league_id)
    if team_id:
        qs = qs.filter(team_id=team_id)

    return list(qs)


# ─────────────────────────────────────────────────────────────────────────────
# INTEREST BOOST ANNOTATION HELPER
# Returns a Case() that gives `weight` when field_name matches ids_list,
# or Value(0.0) unconditionally when the list is empty / filter already applied.
# ─────────────────────────────────────────────────────────────────────────────

def _boost_case(field_name: str, ids_list: list, weight: float,
                skip: bool = False) -> Case:
    """
    skip=True  → already hard-filtering on this dimension, boost adds no info.
    """
    if skip or not ids_list:
        return Value(0.0, output_field=FloatField())

    return Case(
        When(**{f"{field_name}__in": ids_list}, then=Value(weight)),
        default=Value(0.0),
        output_field=FloatField(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN FEED FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def get_short_video_feed(user, league_id=None, team_id=None,
                         bypass_cache: bool = False):
    """
    Returns a plain Python list of ShortVideo instances, ordered by score.

    Parameters
    ----------
    user        : authenticated User instance (required)
    league_id   : str/int – hard-filter to a specific league  (optional)
    team_id     : str/int – hard-filter to a specific team    (optional)
    bypass_cache: always re-score, ignore cached id list      (optional)
    """
    # Normalise to str so cache keys are consistent regardless of caller type
    league_id = str(league_id) if league_id else None
    team_id   = str(team_id)   if team_id   else None

    cache_key = _cache_key(user.pk, league_id=league_id, team_id=team_id)
    ttl       = CACHE_TTL_FILTERED if (league_id or team_id) else CACHE_TTL_GLOBAL

    try:
        # ── Cache hit ─────────────────────────────────────────────────────────
        if not bypass_cache:
            cached_ids = cache.get(cache_key)
            if cached_ids:
                _register_filter_use(user.pk, league_id, team_id)
                return _preserve_order_list(
                    cached_ids,
                    league_id=league_id,
                    team_id=team_id,
                )

        # ── Base queryset ─────────────────────────────────────────────────────
        qs = (
            ShortVideo.objects
            .filter(status='published')
            .select_related('author', 'author__profile', 'league', 'team')
        )

        # ── Hard filters ──────────────────────────────────────────────────────
        if league_id:
            qs = qs.filter(league_id=league_id)
        if team_id:
            qs = qs.filter(team_id=team_id)

        # ── User interest signals ─────────────────────────────────────────────
        exp_leagues   = _user_interest_leagues(user)
        exp_teams     = _user_interest_teams(user)
        hist_leagues  = _user_history_leagues(user)
        hist_teams    = _user_history_teams(user)

        # ── Age in hours (RawSQL works on all PostgreSQL versions) ────────────
        qs = qs.annotate(
            likes_count=F('cached_likes'),
            comments_count=F('cached_comments'),
            shares_count=F('cached_shares'),
            watch_ratio=F('cached_avg_watch_ratio'),
            age_hours=ExpressionWrapper(
                RawSQL(
                    "EXTRACT(EPOCH FROM (NOW() - \"short_videos_shortvideo\".\"created_at\")) / 3600.0",
                    [],
                ),
                output_field=FloatField(),
            ),
        )

        qs = qs.annotate(
            age_hours_capped=Case(
                When(age_hours__gt=AGE_DECAY_CAP_HRS,
                     then=Value(AGE_DECAY_CAP_HRS)),
                default=F('age_hours'),
                output_field=FloatField(),
            )
        )

        # ── Interest boosts ───────────────────────────────────────────────────
        qs = qs.annotate(
            boost_exp_league  = _boost_case('league_id', exp_leagues,
                                            W_EXP_LEAGUE,  skip=bool(league_id)),
            boost_exp_team    = _boost_case('team_id',   exp_teams,
                                            W_EXP_TEAM,    skip=bool(team_id)),
            boost_hist_league = _boost_case('league_id', hist_leagues,
                                            W_HIST_LEAGUE, skip=bool(league_id)),
            boost_hist_team   = _boost_case('team_id',   hist_teams,
                                            W_HIST_TEAM,   skip=bool(team_id)),
        )

        # ── Final score ───────────────────────────────────────────────────────
        qs = qs.annotate(
            score=ExpressionWrapper(
                F('watch_ratio')      * W_WATCH_RATIO
                + F('likes_count')    * W_LIKES
                + F('comments_count') * W_COMMENTS
                + F('shares_count')   * W_SHARES
                + F('age_hours_capped') * (-AGE_DECAY_PER_HOUR)
                + F('boost_exp_league')
                + F('boost_exp_team')
                + F('boost_hist_league')
                + F('boost_hist_team'),
                output_field=FloatField(),
            )
        ).order_by('-score')

        result = list(qs[:FEED_FETCH_SIZE])

        cache.set(cache_key, [str(v.id) for v in result], ttl)
        _register_filter_use(user.pk, league_id, team_id)

        return result

    except Exception as exc:
        import traceback
        print(f"[FEED ERROR] {type(exc).__name__}: {exc}")
        traceback.print_exc()

        # Safe chronological fallback — still respects hard filters
        fallback = ShortVideo.objects.filter(status='published')
        if league_id:
            fallback = fallback.filter(league_id=league_id)
        if team_id:
            fallback = fallback.filter(team_id=team_id)
        return list(fallback.order_by('-created_at')[:30])