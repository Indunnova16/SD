"""
URL configuration for gamification app.
"""

from django.urls import path

from apps.gamification import views

app_name = "gamification"

urlpatterns = [
    # Dashboard
    path("", views.dashboard, name="dashboard"),
    path("stats/", views.dashboard_stats, name="stats"),
    path("overview/", views.dashboard_overview, name="overview"),
    # Points
    path("points/", views.points_history, name="points"),
    path("points/transactions/", views.points_transactions, name="transactions"),
    path("points/by-category/", views.points_by_category, name="points-by-category"),
    # Badges
    path("badges/", views.badges_list, name="badges"),
    path("badges/grid/", views.badges_grid, name="badges-grid"),
    path("badges/<int:badge_id>/", views.badge_detail, name="badge-detail"),
    path("badges/featured/", views.set_featured_badges, name="set-featured"),
    # Leaderboards
    path("leaderboards/", views.leaderboards, name="leaderboards"),
    path("leaderboards/list/", views.leaderboard_list, name="leaderboard-list"),
    path("leaderboards/<slug:slug>/", views.leaderboard_detail, name="leaderboard-detail"),
    # Challenges
    path("challenges/", views.challenges, name="challenges"),
    path("challenges/active/", views.challenges_active, name="challenges-active"),
    path("challenges/my/", views.challenges_user, name="challenges-user"),
    path("challenges/<int:challenge_id>/", views.challenge_detail, name="challenge-detail"),
    path("challenges/<int:challenge_id>/join/", views.join_challenge, name="join-challenge"),
    # Achievements
    path("achievements/", views.achievements, name="achievements"),
    path("achievements/list/", views.achievements_list, name="achievements-list"),
    # Rewards
    path("rewards/", views.rewards, name="rewards"),
    path("rewards/available/", views.rewards_available, name="rewards-available"),
    path("rewards/<int:reward_id>/", views.reward_detail, name="reward-detail"),
    path("rewards/<int:reward_id>/redeem/", views.redeem_reward, name="redeem-reward"),
    path("rewards/history/", views.redemptions_history, name="redemptions-history"),
    # Admin
    path("admin/", views.admin_dashboard, name="admin-dashboard"),
    path("admin/analytics/", views.admin_analytics, name="admin-analytics"),
    path("admin/top-earners/", views.admin_top_earners, name="admin-top-earners"),
    # Team (Coordinador) — issue #58 A9
    path("equipo/", views.team_dashboard, name="team-dashboard"),
    path("equipo/analytics/", views.team_analytics, name="team-analytics"),
    path("equipo/top-earners/", views.team_top_earners, name="team-top-earners"),
]
