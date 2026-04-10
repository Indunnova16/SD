"""
Custom middleware for the SD LMS project.
"""

import time

from django.conf import settings
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin


class SessionInactivityMiddleware(MiddlewareMixin):
    """
    Logs out the user after a period of inactivity.

    Uses SESSION_INACTIVITY_TIMEOUT from settings (default: 600 seconds / 10 min).
    Tracks last activity timestamp in the session and compares it on each request.

    EXCEPTION: Administrators (staff users) have infinite session timeout.
    """

    def process_request(self, request):
        if not request.user.is_authenticated:
            return None

        # Administrators (staff) have infinite session timeout
        if request.user.is_staff:
            request.session["_last_activity"] = time.time()
            return None

        timeout = getattr(settings, "SESSION_INACTIVITY_TIMEOUT", 600)
        now = time.time()
        last_activity = request.session.get("_last_activity")

        if last_activity and (now - last_activity) > timeout:
            logout(request)
            login_url = reverse(settings.LOGIN_URL)
            return redirect(f"{login_url}?timeout=1")

        request.session["_last_activity"] = now
        return None
