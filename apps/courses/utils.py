"""
Utility functions for courses app.
"""

import math


def get_client_ip(request):
    """Get client IP address from request."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    ip = x_forwarded_for.split(",")[0] if x_forwarded_for else request.META.get("REMOTE_ADDR")
    return ip


def round_up_to_half(hours):
    """Round `hours` UP to the nearest 0.5 multiple (SD#62).

    The client requires duration_hours to ALWAYS round up to the nearest
    half-hour, never a standard round() -- e.g. 0.3333h (20 min) must show
    as 0.5, not 0.3.
    """
    return math.ceil(hours * 2) / 2
