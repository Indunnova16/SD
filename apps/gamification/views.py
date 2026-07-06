"""
Views for gamification app.
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.permissions import Rol, require_rol
from apps.gamification.models import (
    Achievement,
    Badge,
    Challenge,
    Reward,
    UserBadge,
    UserChallenge,
)
from apps.gamification.services import (
    AchievementService,
    BadgeService,
    ChallengeService,
    GamificationDashboardService,
    LeaderboardService,
    PointService,
    RewardService,
)

# ============================================================================
# User Dashboard
# ============================================================================


@login_required
def dashboard(request):
    """Main gamification dashboard."""
    return render(request, "gamification/dashboard.html")


@login_required
@require_GET
def dashboard_stats(request):
    """Get dashboard stats (HTMX partial)."""
    stats = PointService.get_user_stats(request.user)
    return render(request, "gamification/partials/stats.html", {"stats": stats})


@login_required
@require_GET
def dashboard_overview(request):
    """Get full dashboard overview (HTMX partial)."""
    data = GamificationDashboardService.get_user_dashboard(request.user)
    return render(request, "gamification/partials/overview.html", data)


# ============================================================================
# Points
# ============================================================================


@login_required
def points_history(request):
    """User's points history page."""
    return render(request, "gamification/points.html")


@login_required
@require_GET
def points_transactions(request):
    """Get points transactions (HTMX partial)."""
    limit = max(1, int(request.GET.get("limit", 50)))  # Ensure positive limit
    transactions = PointService.get_transaction_history(request.user, limit=limit)
    return render(
        request,
        "gamification/partials/transactions.html",
        {"transactions": transactions},
    )


@login_required
@require_GET
def points_by_category(request):
    """Get points breakdown by category (HTMX partial)."""
    stats = PointService.get_user_stats(request.user)
    return render(
        request,
        "gamification/partials/points_by_category.html",
        {"categories": stats["points_by_category"]},
    )


# ============================================================================
# Badges
# ============================================================================


@login_required
def badges_list(request):
    """User's badges page."""
    return render(request, "gamification/badges.html")


@login_required
@require_GET
def badges_grid(request):
    """Get badges grid (HTMX partial)."""
    data = BadgeService.get_user_badges(request.user)
    all_badges = (
        Badge.objects.filter(is_active=True, is_secret=False)
        .select_related("category")
        .order_by("category__order", "rarity", "name")
    )

    # Mark which badges user has
    earned_ids = {ub.badge_id for ub in data["badges"]}

    return render(
        request,
        "gamification/partials/badges_grid.html",
        {
            "all_badges": all_badges,
            "earned_ids": earned_ids,
            "data": data,
        },
    )


@login_required
def badge_detail(request, badge_id):
    """Badge detail modal."""
    badge = get_object_or_404(Badge, id=badge_id)
    user_badge = UserBadge.objects.filter(user=request.user, badge=badge).first()

    return render(
        request,
        "gamification/partials/badge_detail.html",
        {"badge": badge, "user_badge": user_badge},
    )


@login_required
@require_POST
def set_featured_badges(request):
    """Set featured badges."""
    badge_ids = request.POST.getlist("badge_ids")
    badge_ids = [int(bid) for bid in badge_ids if bid.isdigit()]

    BadgeService.set_featured_badges(request.user, badge_ids)

    return render(
        request,
        "gamification/partials/featured_badges.html",
        {"featured": BadgeService.get_featured_badges(request.user)},
    )


# ============================================================================
# Leaderboards
# ============================================================================


@login_required
def leaderboards(request):
    """Leaderboards page."""
    return render(request, "gamification/leaderboards.html")


@login_required
@require_GET
def leaderboard_list(request):
    """Get all leaderboards (HTMX partial)."""
    data = LeaderboardService.get_all_leaderboards()
    return render(
        request,
        "gamification/partials/leaderboard_list.html",
        {"leaderboards": data},
    )


@login_required
@require_GET
def leaderboard_detail(request, slug):
    """Get specific leaderboard entries."""
    limit = max(1, int(request.GET.get("limit", 20)))  # Ensure positive limit
    data = LeaderboardService.get_leaderboard_entries(
        leaderboard_slug=slug,
        limit=limit,
        user=request.user,
    )

    return render(
        request,
        "gamification/partials/leaderboard_entries.html",
        data,
    )


# ============================================================================
# Challenges
# ============================================================================


@login_required
def challenges(request):
    """Challenges page."""
    return render(request, "gamification/challenges.html")


@login_required
@require_GET
def challenges_active(request):
    """Get active challenges (HTMX partial)."""
    data = ChallengeService.get_active_challenges(request.user)
    return render(
        request,
        "gamification/partials/challenges_active.html",
        {"challenges": data},
    )


@login_required
@require_GET
def challenges_user(request):
    """Get user's challenges (HTMX partial)."""
    data = ChallengeService.get_user_challenges(request.user)
    return render(
        request,
        "gamification/partials/challenges_user.html",
        data,
    )


@login_required
def challenge_detail(request, challenge_id):
    """Challenge detail page."""
    challenge = get_object_or_404(Challenge, id=challenge_id)
    participation = UserChallenge.objects.filter(user=request.user, challenge=challenge).first()

    return render(
        request,
        "gamification/partials/challenge_detail.html",
        {"challenge": challenge, "participation": participation},
    )


@login_required
@require_POST
def join_challenge(request, challenge_id):
    """Join a challenge."""
    participation = ChallengeService.join_challenge(request.user, challenge_id)

    if participation:
        return render(
            request,
            "gamification/partials/challenge_joined.html",
            {"participation": participation},
        )
    else:
        return JsonResponse({"error": "Unable to join challenge"}, status=400)


# ============================================================================
# Achievements
# ============================================================================


@login_required
def achievements(request):
    """Achievements page."""
    return render(request, "gamification/achievements.html")


@login_required
@require_GET
def achievements_list(request):
    """Get achievements list (HTMX partial)."""
    data = AchievementService.get_user_achievements(request.user)
    all_achievements = Achievement.objects.filter(is_active=True).order_by("order")

    unlocked_ids = {ua.achievement_id for ua in data["unlocked"]}

    return render(
        request,
        "gamification/partials/achievements_list.html",
        {
            "all_achievements": all_achievements,
            "unlocked_ids": unlocked_ids,
            "data": data,
        },
    )


# ============================================================================
# Rewards
# ============================================================================


@login_required
def rewards(request):
    """Rewards store page."""
    return render(request, "gamification/rewards.html")


@login_required
@require_GET
def rewards_available(request):
    """Get available rewards (HTMX partial)."""
    data = RewardService.get_available_rewards(request.user)
    user_points = PointService.get_or_create_user_points(request.user)

    return render(
        request,
        "gamification/partials/rewards_available.html",
        {
            "rewards": data,
            "available_points": user_points.available_points,
        },
    )


@login_required
def reward_detail(request, reward_id):
    """Reward detail modal."""
    reward = get_object_or_404(Reward, id=reward_id)
    user_points = PointService.get_or_create_user_points(request.user)

    can_afford = user_points.available_points >= reward.points_cost
    level_ok = True
    if reward.min_level:
        level_ok = user_points.level and user_points.level.number >= reward.min_level.number

    return render(
        request,
        "gamification/partials/reward_detail.html",
        {
            "reward": reward,
            "can_afford": can_afford,
            "level_ok": level_ok,
            "available_points": user_points.available_points,
        },
    )


@login_required
@require_POST
def redeem_reward(request, reward_id):
    """Redeem a reward."""
    notes = request.POST.get("notes", "")
    redemption = RewardService.redeem_reward(request.user, reward_id, notes)

    if redemption:
        return render(
            request,
            "gamification/partials/reward_redeemed.html",
            {"redemption": redemption},
        )
    else:
        return JsonResponse({"error": "Unable to redeem reward"}, status=400)


@login_required
@require_GET
def redemptions_history(request):
    """Get user's redemption history (HTMX partial)."""
    redemptions = RewardService.get_user_redemptions(request.user)
    return render(
        request,
        "gamification/partials/redemptions_history.html",
        {"redemptions": redemptions},
    )


# ============================================================================
# Admin Dashboard
# ============================================================================


@login_required
@require_rol(Rol.ADMINISTRADOR, redirect_url="gamification:dashboard")
def admin_dashboard(request):
    """Admin gamification dashboard."""
    return render(request, "gamification/admin/dashboard.html")


@login_required
@require_GET
@require_rol(Rol.ADMINISTRADOR, redirect_url="gamification:dashboard")
def admin_analytics(request):
    """Get admin analytics (HTMX partial)."""
    data = GamificationDashboardService.get_admin_analytics()
    return render(
        request,
        "gamification/admin/partials/analytics.html",
        data,
    )


@login_required
@require_GET
@require_rol(Rol.ADMINISTRADOR, redirect_url="gamification:dashboard")
def admin_top_earners(request):
    """Get top earners this week (HTMX partial)."""
    data = GamificationDashboardService.get_admin_analytics()
    return render(
        request,
        "gamification/admin/partials/top_earners.html",
        {"top_earners": data["users"]["top_earners"]},
    )


# ============================================================================
# Team Dashboard (Coordinador) — issue #58 A9
# ============================================================================
#
# Filtrado de datos de Gamificación por rol: propio (dashboard de arriba,
# sin cambio) / equipo (acá, NUEVO — Coordinador vía `User.supervisor` FK
# de A1, `related_name='equipo'`) / todo (Admin dashboard de arriba, ya
# migrado por A4 a `require_rol(ADMINISTRADOR)`). Reusa los MISMOS partials
# de "Admin" (`gamification/admin/partials/analytics.html` y
# `.../top_earners.html`) porque el shape de contexto es idéntico — solo
# cambia qué datos trae el service (`get_team_analytics` vs
# `get_admin_analytics`), no cómo se renderizan.


@login_required
@require_rol(Rol.COORDINADOR, Rol.ADMINISTRADOR, redirect_url="gamification:dashboard")
def team_dashboard(request):
    """
    Dashboard de gamificación del equipo. Ranking/puntos SOLO de los
    usuarios que reportan a `request.user` vía `User.supervisor` FK.
    Accesible a Coordinador (su equipo) y Administrador (a quien supervisa
    directamente — alcance distinto de "todo el sistema" de `admin_dashboard`).
    """
    return render(request, "gamification/team/dashboard.html")


@login_required
@require_GET
@require_rol(Rol.COORDINADOR, Rol.ADMINISTRADOR, redirect_url="gamification:dashboard")
def team_analytics(request):
    """Get team analytics (HTMX partial) — acotado al equipo de `request.user`."""
    data = GamificationDashboardService.get_team_analytics(request.user)
    return render(
        request,
        "gamification/admin/partials/analytics.html",
        data,
    )


@login_required
@require_GET
@require_rol(Rol.COORDINADOR, Rol.ADMINISTRADOR, redirect_url="gamification:dashboard")
def team_top_earners(request):
    """Get team's top earners this week (HTMX partial) — acotado al equipo."""
    data = GamificationDashboardService.get_team_analytics(request.user)
    return render(
        request,
        "gamification/admin/partials/top_earners.html",
        {"top_earners": data["users"]["top_earners"]},
    )
