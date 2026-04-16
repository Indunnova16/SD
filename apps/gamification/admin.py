"""
Admin configuration for gamification app.
"""

from django.contrib import admin
from django.utils.html import format_html

from apps.gamification.models import (
    Achievement,
    Badge,
    BadgeCategory,
    Challenge,
    Leaderboard,
    LeaderboardEntry,
    Level,
    PointCategory,
    PointTransaction,
    Reward,
    RewardRedemption,
    UserAchievement,
    UserBadge,
    UserChallenge,
    UserPoints,
)


@admin.register(PointCategory)
class PointCategoryAdmin(admin.ModelAdmin):
    """Admin for point categories."""

    list_display = ["name", "slug", "multiplier", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(PointTransaction)
class PointTransactionAdmin(admin.ModelAdmin):
    """Admin for point transactions."""

    list_display = [
        "user",
        "category",
        "transaction_type",
        "points_display",
        "description",
        "created_at",
    ]
    list_filter = ["transaction_type", "category", "created_at"]
    search_fields = ["user__email", "description"]
    readonly_fields = ["created_at"]
    date_hierarchy = "created_at"

    @admin.display(description="Points")
    def points_display(self, obj):
        """Display points with color."""
        if obj.points >= 0:
            return format_html('<span style="color: green;">+{}</span>', obj.points)
        return format_html('<span style="color: red;">{}</span>', obj.points)


@admin.register(Level)
class LevelAdmin(admin.ModelAdmin):
    """Admin for levels."""

    list_display = ["number", "name", "min_points", "max_points", "icon", "color"]
    ordering = ["number"]


@admin.register(UserPoints)
class UserPointsAdmin(admin.ModelAdmin):
    """Admin for user points."""

    list_display = [
        "user",
        "total_points",
        "available_points",
        "level",
        "current_streak",
        "longest_streak",
    ]
    list_filter = ["level"]
    search_fields = ["user__email"]
    readonly_fields = ["total_points", "weekly_points", "monthly_points"]


@admin.register(BadgeCategory)
class BadgeCategoryAdmin(admin.ModelAdmin):
    """Admin for badge categories."""

    list_display = ["name", "slug", "icon", "order"]
    prepopulated_fields = {"slug": ("name",)}
    ordering = ["order", "name"]


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    """Admin for badges."""

    list_display = [
        "name",
        "category",
        "rarity",
        "points_reward",
        "times_awarded",
        "is_secret",
        "is_active",
    ]
    list_filter = ["category", "rarity", "is_secret", "is_active"]
    search_fields = ["name", "description"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(UserBadge)
class UserBadgeAdmin(admin.ModelAdmin):
    """Admin for user badges."""

    list_display = ["user", "badge", "earned_at", "is_featured"]
    list_filter = ["badge__category", "badge__rarity", "is_featured"]
    search_fields = ["user__email", "badge__name"]
    date_hierarchy = "earned_at"


@admin.register(Leaderboard)
class LeaderboardAdmin(admin.ModelAdmin):
    """Admin for leaderboards."""

    list_display = ["name", "period", "scope", "point_category", "is_active"]
    list_filter = ["period", "scope", "is_active"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(LeaderboardEntry)
class LeaderboardEntryAdmin(admin.ModelAdmin):
    """Admin for leaderboard entries."""

    list_display = ["leaderboard", "rank", "user", "points", "period_start", "period_end"]
    list_filter = ["leaderboard", "period_start"]
    search_fields = ["user__email"]
    ordering = ["leaderboard", "rank"]


@admin.register(Challenge)
class ChallengeAdmin(admin.ModelAdmin):
    """Admin for challenges."""

    list_display = [
        "name",
        "challenge_type",
        "status",
        "start_date",
        "end_date",
        "target_value",
        "points_reward",
    ]
    list_filter = ["challenge_type", "status"]
    search_fields = ["name", "description"]
    prepopulated_fields = {"slug": ("name",)}
    date_hierarchy = "start_date"


@admin.register(UserChallenge)
class UserChallengeAdmin(admin.ModelAdmin):
    """Admin for user challenges."""

    list_display = [
        "user",
        "challenge",
        "status",
        "current_value",
        "progress_percentage",
        "enrolled_at",
    ]
    list_filter = ["status", "challenge"]
    search_fields = ["user__email", "challenge__name"]

    @admin.display(description="Progress")
    def progress_percentage(self, obj):
        """Display progress bar."""
        pct = obj.progress_percentage
        color = "success" if pct >= 100 else "info" if pct >= 50 else "warning"
        return format_html(
            '<div style="width:100px;background:#ddd;border-radius:4px;">'
            '<div style="width:{}px;background:{};height:10px;border-radius:4px;"></div>'
            "</div> {}%",
            pct,
            {"success": "#28a745", "info": "#17a2b8", "warning": "#ffc107"}[color],
            pct,
        )


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    """Admin for achievements."""

    list_display = [
        "name",
        "achievement_type",
        "points_reward",
        "badge",
        "is_repeatable",
        "is_active",
        "order",
    ]
    list_filter = ["achievement_type", "is_repeatable", "is_active"]
    search_fields = ["name", "description"]
    prepopulated_fields = {"slug": ("name",)}
    ordering = ["order", "name"]


@admin.register(UserAchievement)
class UserAchievementAdmin(admin.ModelAdmin):
    """Admin for user achievements."""

    list_display = ["user", "achievement", "unlocked_at", "times_unlocked"]
    list_filter = ["achievement__achievement_type"]
    search_fields = ["user__email", "achievement__name"]
    date_hierarchy = "unlocked_at"


@admin.register(Reward)
class RewardAdmin(admin.ModelAdmin):
    """Admin for rewards."""

    list_display = [
        "name",
        "reward_type",
        "points_cost",
        "quantity_available",
        "quantity_redeemed",
        "is_active",
    ]
    list_filter = ["reward_type", "is_active"]
    search_fields = ["name", "description"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(RewardRedemption)
class RewardRedemptionAdmin(admin.ModelAdmin):
    """Admin for reward redemptions."""

    list_display = [
        "user",
        "reward",
        "status",
        "points_spent",
        "redeemed_at",
        "fulfilled_at",
    ]
    list_filter = ["status", "reward"]
    search_fields = ["user__email", "reward__name"]
    date_hierarchy = "redeemed_at"
