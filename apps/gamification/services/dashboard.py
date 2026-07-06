"""
Dashboard service for gamification.

Provides comprehensive dashboard and analytics functionality.
"""

from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone

from apps.gamification.models import (
    Challenge,
    PointTransaction,
    UserBadge,
    UserChallenge,
)


class GamificationDashboardService:
    """Service for gamification dashboard and analytics."""

    @staticmethod
    def get_user_dashboard(user) -> dict:
        """Get comprehensive gamification dashboard for user."""
        from apps.gamification.services.achievements import AchievementService
        from apps.gamification.services.badges import BadgeService
        from apps.gamification.services.challenges import ChallengeService
        from apps.gamification.services.points import PointService

        return {
            "stats": PointService.get_user_stats(user),
            "badges": BadgeService.get_user_badges(user),
            "featured_badges": BadgeService.get_featured_badges(user),
            "achievements": AchievementService.get_user_achievements(user),
            "challenges": ChallengeService.get_user_challenges(user),
            "recent_transactions": PointService.get_transaction_history(user, limit=10),
        }

    @staticmethod
    def _compute_analytics(supervisor=None) -> dict:
        """
        Agregados de puntos/insignias/usuarios/desafíos, con alcance
        opcionalmente acotado a un equipo (issue #58 A9).

        `supervisor=None` (default): alcance GLOBAL, todo el sistema — usado
        por `get_admin_analytics()` (Administrador).
        `supervisor=<user>`: alcance EQUIPO — SOLO usuarios con
        `User.supervisor == supervisor` (FK de A1, `related_name='equipo'`) —
        usado por `get_team_analytics()` (Coordinador). Los 3 modelos que se
        agregan (`PointTransaction`, `UserBadge`, `UserChallenge`) tienen
        todos una FK directa `user`, así que el mismo filtro
        `user__supervisor=supervisor` aplica a los tres sin traducción.
        Un Coordinador sin nadie a cargo (equipo vacío) obtiene ceros/listas
        vacías — el filtro simplemente no matchea ningún registro, nunca una
        excepción.

        `Challenge` (a diferencia de los anteriores) es una campaña GLOBAL
        del sistema, no pertenece a ningún equipo — su conteo de "activos"
        es el mismo para alcance global o equipo (no existe un "desafío del
        equipo de X"). Lo que sí se acota por equipo es cuántos de ESE
        equipo los completaron (`UserChallenge`).
        """
        scope_filter = {"user__supervisor": supervisor} if supervisor is not None else {}

        now = timezone.now()
        today = now.date()
        week_start = today - timedelta(days=today.weekday())

        # Point statistics
        total_points = (
            PointTransaction.objects.filter(points__gt=0, **scope_filter).aggregate(
                total=Sum("points")
            )["total"]
            or 0
        )

        points_today = (
            PointTransaction.objects.filter(
                created_at__date=today, points__gt=0, **scope_filter
            ).aggregate(total=Sum("points"))["total"]
            or 0
        )

        points_this_week = (
            PointTransaction.objects.filter(
                created_at__date__gte=week_start, points__gt=0, **scope_filter
            ).aggregate(total=Sum("points"))["total"]
            or 0
        )

        # Badge statistics
        total_badges_awarded = UserBadge.objects.filter(**scope_filter).count()

        # Active users (with points this week)
        active_users = (
            PointTransaction.objects.filter(created_at__date__gte=week_start, **scope_filter)
            .values("user")
            .distinct()
            .count()
        )

        # Top earners this week
        top_earners = (
            PointTransaction.objects.filter(
                created_at__date__gte=week_start, points__gt=0, **scope_filter
            )
            .values("user", "user__email", "user__first_name", "user__last_name")
            .annotate(total=Sum("points"))
            .order_by("-total")[:10]
        )

        # Challenge statistics
        active_challenges = Challenge.objects.filter(
            status=Challenge.Status.ACTIVE,
            start_date__lte=now,
            end_date__gte=now,
        ).count()

        completed_challenges = UserChallenge.objects.filter(
            status=UserChallenge.Status.COMPLETED, **scope_filter
        ).count()

        return {
            "points": {
                "total": total_points,
                "today": points_today,
                "this_week": points_this_week,
            },
            "badges": {
                "total_awarded": total_badges_awarded,
            },
            "users": {
                "active_this_week": active_users,
                "top_earners": list(top_earners),
            },
            "challenges": {
                "active": active_challenges,
                "completed": completed_challenges,
            },
        }

    @staticmethod
    def get_admin_analytics() -> dict:
        """Get gamification analytics for admins (alcance GLOBAL, todo el sistema)."""
        return GamificationDashboardService._compute_analytics()

    @staticmethod
    def get_team_analytics(supervisor) -> dict:
        """
        Get gamification analytics scoped to `supervisor`'s equipo (issue
        #58 A9) — Coordinador ve ranking/puntos SOLO de los usuarios con
        `User.supervisor == supervisor`, nunca del sistema completo ni del
        equipo de otro Coordinador. Ver `_compute_analytics` para el detalle
        de qué se acota y qué queda global (`Challenge`).
        """
        return GamificationDashboardService._compute_analytics(supervisor=supervisor)
