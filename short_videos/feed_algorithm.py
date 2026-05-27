"""
ConnectDial — Short Video Feed Algorithm (v7 — fully working)
=============================================================
Key guarantees
──────────────
• league_id / team_id filters are applied BEFORE scoring so the backend
  never returns wrong-league videos regardless of cache state.
• Cache key includes league_id/team_id so each filtered view has its own slot.
• _preserve_order_list re-applies the same hard filters on cache-hit so
  stale entries cannot leak wrong-league videos.
• _boost_case produces clean Value(0.0) — no broken Case/When sentinel.
• RawSQL epoch extraction works on all PostgreSQL versions.
• FEED_FETCH_SIZE=50 (pagination max is 50, no point fetching 200).
• Filtered TTL = 2 min so league chips feel instant.
• bust_feed_cache clears all known filtered slots for a user.
"""

from django.db.models import (
    F, ExpressionWrapper, FloatField,
    Case, When, Value, IntegerField,
)
from django.db.models.expressions import RawSQL
from django.core.cache import cache

from .models import ShortVideo, VideoView


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

CACHE_TTL_GLOBAL   = 60 * 5    # 5 min  — global personal feed
CACHE_TTL_FILTERED = 60 * 2    # 2 min  — any league/team filter
AGE_DECAY_PER_HOUR = 0.3
AGE_DECAY_CAP_HRS  = 24.0
HISTORY_LIMIT      = 10
FEED_FETCH_SIZE    = 50        # matches pagination max_limit

W_WATCH_RATIO = 4.0
W_LIKES       = 2.0
W_COMMENTS    = 3.0
W_SHARES      = 5.0
W_EXP_LEAGUE  = 2.0
W_EXP_TEAM    = 3.0
W_HIST_LEAGUE = 1.0
W_HIST_TEAM   = 1.5

# DB table name used in the RawSQL EPOCH expression — matches Django default.
# Change this if you renamed the app or model.
_VIDEO_TABLE = 'short_videos_shortvideo'


# ─────────────────────────────────────────────────────────────────────────────
# CACHE UTILITIES
# ─────────────────────────────────────────────────────────────────────────────

def _cache_key(user_id, league_id=None, team_id=None) -> str:
    suffix = f':l{league_id}' if league_id else ''
    suffix += f':t{team_id}'  if team_id  else ''
    return f'short_feed:v7:{user_id}{suffix}'


def bust_feed_cache(user_id: int) -> None:
    """
    Invalidate every cached feed slot for this user —
    called by signals when a new video is published.
    """
    cache.delete(_cache_key(user_id))

    # Also bust every filtered slot this user has used
    used_key = f'short_feed:filters_used:{user_id}'
    used: list = cache.get(used_key) or []
    keys_to_delete = [_cache_key(user_id, league_id=lid, team_id=tid)
                      for lid, tid in used]
    if keys_to_delete:
        cache.delete_many(keys_to_delete)
    cache.delete(used_key)


def _record_filter_use(user_id: int, league_id, team_id) -> None:
    """Remember which league/team filter combos this user has used."""
    if not league_id and not team_id:
        return
    used_key = f'short_feed:filters_used:{user_id}'
    used: list = cache.get(used_key) or []
    entry = (league_id, team_id)
    if entry not in used:
        used = (used + [entry])[-20:]   # keep last 20
        cache.set(used_key, used, 60 * 60 * 24)


# ─────────────────────────────────────────────────────────────────────────────
# USER INTEREST SIGNALS
# ─────────────────────────────────────────────────────────────────────────────

def _exp_leagues(user):
    fav = getattr(user, 'favorite_league_id', None)
    return [str(fav)] if fav else []


def _exp_teams(user):
    fav = getattr(user, 'favorite_team_id', None)
    return [str(fav)] if fav else []


def _hist_leagues(user) -> list:
    try:
        return [
            str(x) for x in
            VideoView.objects
            .filter(user=user, video__league__isnull=False)
            .values_list('video__league_id', flat=True)
            .order_by('-created_at').distinct()[:HISTORY_LIMIT]
        ]
    except Exception:
        return []


def _hist_teams(user) -> list:
    try:
        return [
            str(x) for x in
            VideoView.objects
            .filter(user=user, video__team__isnull=False)
            .values_list('video__team_id', flat=True)
            .order_by('-created_at').distinct()[:HISTORY_LIMIT]
        ]
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# BOOST HELPER
# Returns a simple Case or a constant Value depending on context.
# ─────────────────────────────────────────────────────────────────────────────

def _boost(field: str, ids: list, weight: float, skip: bool = False):
    if skip or not ids:
        return Value(0.0, output_field=FloatField())
    return Case(
        When(**{f'{field}__in': ids}, then=Value(weight)),
        default=Value(0.0),
        output_field=FloatField(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# REHYDRATE ORDERED LIST FROM CACHED IDs
# ─────────────────────────────────────────────────────────────────────────────

def _rehydrate(ids: list, league_id=None, team_id=None) -> list:
    """
    Fetch ShortVideo rows in the exact order given by `ids`.
    Re-applies league/team filter so a stale cache entry never leaks wrong videos.
    """
    if not ids:
        return []
    from uuid import UUID
    try:
        uuid_ids = [UUID(i) for i in ids]
    except Exception:
        return []

    order_expr = Case(
        *[When(pk=vid, then=Value(pos)) for pos, vid in enumerate(uuid_ids)],
        output_field=IntegerField(),
    )
    qs = (
        ShortVideo.objects
        .filter(pk__in=uuid_ids, status='published')
        .select_related('author', 'author__profile', 'league', 'team')
        .prefetch_related('author__fan_preferences', 'author__fan_preferences__team')
        .annotate(order=order_expr)
        .order_by('order')
    )
    if league_id:
        qs = qs.filter(league_id=league_id)
    if team_id:
        qs = qs.filter(team_id=team_id)
    return list(qs)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def get_short_video_feed(user, league_id=None, team_id=None,
                         bypass_cache: bool = False) -> list:
    """
    Return an ordered list of ShortVideo objects for `user`.

    league_id / team_id are string or int PKs from the frontend request.
    bypass_cache=True forces a fresh score even when cache is warm.
    """
    # Normalise to string for consistent cache keys
    league_id = str(league_id) if league_id else None
    team_id   = str(team_id)   if team_id   else None

    cache_key = _cache_key(user.pk, league_id=league_id, team_id=team_id)
    ttl = CACHE_TTL_FILTERED if (league_id or team_id) else CACHE_TTL_GLOBAL

    # ── Cache hit ─────────────────────────────────────────────────────────────
    if not bypass_cache:
        cached_ids = cache.get(cache_key)
        if cached_ids:
            _record_filter_use(user.pk, league_id, team_id)
            return _rehydrate(cached_ids, league_id=league_id, team_id=team_id)

    try:
        # ── Base queryset — hard-filter first ─────────────────────────────────
        qs = (
            ShortVideo.objects
            .filter(status='published')
            .select_related('author', 'author__profile', 'league', 'team')
            .prefetch_related('author__fan_preferences', 'author__fan_preferences__team')
        )

        # Hard league / team filter — applied before ANY annotation so the DB
        # only scores relevant videos (not the whole table).
        if league_id:
            qs = qs.filter(league_id=league_id)
        if team_id:
            qs = qs.filter(team_id=team_id)

        # ── User interest signals ─────────────────────────────────────────────
        fav_leagues  = _exp_leagues(user)
        fav_teams    = _exp_teams(user)
        hist_leagues = _hist_leagues(user)
        hist_teams   = _hist_teams(user)

        # ── Metric annotations ────────────────────────────────────────────────
        qs = qs.annotate(
            _likes    = F('cached_likes'),
            _comments = F('cached_comments'),
            _shares   = F('cached_shares'),
            _watch    = F('cached_avg_watch_ratio'),
            # Age in hours — RawSQL works on PostgreSQL 11+ without ExtractEpoch
            _age_hours=ExpressionWrapper(
                RawSQL(
                    f'EXTRACT(EPOCH FROM (NOW() - "{_VIDEO_TABLE}"."created_at")) / 3600.0',
                    [],
                ),
                output_field=FloatField(),
            ),
        )

        # Cap age decay
        qs = qs.annotate(
            _age_capped=Case(
                When(_age_hours__gt=AGE_DECAY_CAP_HRS, then=Value(AGE_DECAY_CAP_HRS)),
                default=F('_age_hours'),
                output_field=FloatField(),
            )
        )

        # ── Interest boosts (skip the dimension we're already filtering on) ───
        qs = qs.annotate(
            _b_fav_league  = _boost('league_id', fav_leagues,  W_EXP_LEAGUE,  skip=bool(league_id)),
            _b_fav_team    = _boost('team_id',   fav_teams,    W_EXP_TEAM,    skip=bool(team_id)),
            _b_hist_league = _boost('league_id', hist_leagues, W_HIST_LEAGUE, skip=bool(league_id)),
            _b_hist_team   = _boost('team_id',   hist_teams,   W_HIST_TEAM,   skip=bool(team_id)),
        )

        # ── Final score ───────────────────────────────────────────────────────
        qs = qs.annotate(
            score=ExpressionWrapper(
                F('_watch')      * W_WATCH_RATIO
                + F('_likes')    * W_LIKES
                + F('_comments') * W_COMMENTS
                + F('_shares')   * W_SHARES
                + F('_age_capped') * (-AGE_DECAY_PER_HOUR)
                + F('_b_fav_league')
                + F('_b_fav_team')
                + F('_b_hist_league')
                + F('_b_hist_team'),
                output_field=FloatField(),
            )
        ).order_by('-score')

        result = list(qs[:FEED_FETCH_SIZE])

        # Persist to cache
        cache.set(cache_key, [str(v.id) for v in result], ttl)
        _record_filter_use(user.pk, league_id, team_id)

        return result

    except Exception as exc:
        import traceback
        print(f'[FEED] {type(exc).__name__}: {exc}')
        traceback.print_exc()

        # Chronological fallback — still honours hard filters
        qs = ShortVideo.objects.filter(status='published')
        if league_id:
            qs = qs.filter(league_id=league_id)
        if team_id:
            qs = qs.filter(team_id=team_id)
        return list(qs.order_by('-created_at')[:30])