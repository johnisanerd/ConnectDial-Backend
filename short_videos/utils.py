"""
ConnectDial — Utils
====================
Legacy utility kept for backwards compatibility.
New code should import directly from feed_algorithm.
"""

from .feed_algorithm import get_short_video_feed, bust_feed_cache

__all__ = ['get_short_video_feed', 'bust_feed_cache']