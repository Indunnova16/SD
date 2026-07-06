"""
Factory classes for gamification tests.

Uses factory_boy to create test data for all gamification models.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

import factory
from factory.django import DjangoModelFactory

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

User = get_user_model()


class UserFactory(DjangoModelFactory):
    """Factory for User model."""

    class Meta:
        model = User
        django_get_or_create = ("email",)

    email = factory.Sequence(lambda n: f"user{n}@test.com")
    password = factory.PostGenerationMethodCall("set_password", "testpass123")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    document_type = "CC"
    document_number = factory.Sequence(lambda n: f"{10000000 + n}")
    job_position = "Technician"
    hire_date = factory.LazyFunction(lambda: date.today() - timedelta(days=365))
    is_active = True


class AdminUserFactory(UserFactory):
    """Factory for admin users.

    `rol=ADMINISTRADOR` (issue #58, RBAC): el gating de negocio ya no lee
    `is_staff`/`is_superuser` sino `user.rol` — se mantienen ambos flags
    porque siguen dando acceso a `/admin/` de Django, pero un
    `AdminUserFactory()` debe representar tambien al rol de acceso real.
    """

    email = factory.Sequence(lambda n: f"admin{n}@test.com")
    is_staff = True
    is_superuser = True
    rol = User.Rol.ADMINISTRADOR


class PointCategoryFactory(DjangoModelFactory):
    """Factory for PointCategory model."""

    class Meta:
        model = PointCategory
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Point Category {n}")
    slug = factory.Sequence(lambda n: f"category-{n}")
    description = factory.Faker("sentence")
    icon = "star"
    color = "primary"
    multiplier = Decimal("1.0")
    is_active = True


class LevelFactory(DjangoModelFactory):
    """Factory for Level model."""

    class Meta:
        model = Level
        django_get_or_create = ("number",)

    number = factory.Sequence(lambda n: n + 1)
    name = factory.LazyAttribute(lambda obj: f"Level {obj.number}")
    min_points = factory.LazyAttribute(lambda obj: obj.number * 100)
    max_points = factory.LazyAttribute(lambda obj: (obj.number + 1) * 100 - 1)
    icon = "trophy"
    color = "primary"
    benefits = factory.LazyFunction(list)


class UserPointsFactory(DjangoModelFactory):
    """Factory for UserPoints model."""

    class Meta:
        model = UserPoints
        django_get_or_create = ("user",)

    user = factory.SubFactory(UserFactory)
    total_points = 0
    available_points = 0
    level = None
    current_streak = 0
    longest_streak = 0
    last_activity_date = None
    weekly_points = 0
    monthly_points = 0


class PointTransactionFactory(DjangoModelFactory):
    """Factory for PointTransaction model."""

    class Meta:
        model = PointTransaction

    user = factory.SubFactory(UserFactory)
    category = factory.SubFactory(PointCategoryFactory)
    transaction_type = PointTransaction.TransactionType.EARNED
    points = factory.Faker("random_int", min=10, max=100)
    description = factory.Faker("sentence")
    reference_type = ""
    reference_id = None
    metadata = factory.LazyFunction(dict)


class BadgeCategoryFactory(DjangoModelFactory):
    """Factory for BadgeCategory model."""

    class Meta:
        model = BadgeCategory
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Badge Category {n}")
    slug = factory.Sequence(lambda n: f"badge-cat-{n}")
    description = factory.Faker("sentence")
    icon = "award"
    order = factory.Sequence(lambda n: n)


class BadgeFactory(DjangoModelFactory):
    """Factory for Badge model."""

    class Meta:
        model = Badge
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Badge {n}")
    slug = factory.Sequence(lambda n: f"badge-{n}")
    description = factory.Faker("paragraph")
    category = factory.SubFactory(BadgeCategoryFactory)
    icon = "medal"
    rarity = Badge.Rarity.COMMON
    points_reward = 50
    criteria = factory.LazyFunction(dict)
    is_secret = False
    is_active = True
    max_awards = None
    times_awarded = 0


class UserBadgeFactory(DjangoModelFactory):
    """Factory for UserBadge model."""

    class Meta:
        model = UserBadge
        django_get_or_create = ("user", "badge")

    user = factory.SubFactory(UserFactory)
    badge = factory.SubFactory(BadgeFactory)
    reference_type = ""
    reference_id = None
    is_featured = False
    metadata = factory.LazyFunction(dict)


class LeaderboardFactory(DjangoModelFactory):
    """Factory for Leaderboard model."""

    class Meta:
        model = Leaderboard
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Leaderboard {n}")
    slug = factory.Sequence(lambda n: f"leaderboard-{n}")
    description = factory.Faker("sentence")
    period = Leaderboard.Period.WEEKLY
    scope = Leaderboard.Scope.GLOBAL
    point_category = None
    max_entries = 100
    is_active = True
    reset_date = None
    metadata = factory.LazyFunction(dict)


class LeaderboardEntryFactory(DjangoModelFactory):
    """Factory for LeaderboardEntry model."""

    class Meta:
        model = LeaderboardEntry

    leaderboard = factory.SubFactory(LeaderboardFactory)
    user = factory.SubFactory(UserFactory)
    rank = factory.Sequence(lambda n: n + 1)
    points = factory.Faker("random_int", min=100, max=1000)
    previous_rank = None
    period_start = factory.LazyFunction(lambda: timezone.now().date())
    period_end = factory.LazyFunction(lambda: timezone.now().date() + timedelta(days=7))
    metadata = factory.LazyFunction(dict)


class ChallengeFactory(DjangoModelFactory):
    """Factory for Challenge model."""

    class Meta:
        model = Challenge
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Challenge {n}")
    slug = factory.Sequence(lambda n: f"challenge-{n}")
    description = factory.Faker("paragraph")
    challenge_type = Challenge.ChallengeType.INDIVIDUAL
    status = Challenge.Status.ACTIVE
    start_date = factory.LazyFunction(lambda: timezone.now() - timedelta(hours=1))
    end_date = factory.LazyFunction(lambda: timezone.now() + timedelta(days=7))
    target_value = 100
    target_metric = "points"
    points_reward = 100
    badge_reward = None
    max_participants = None
    criteria = factory.LazyFunction(dict)
    rules = factory.Faker("paragraph")
    metadata = factory.LazyFunction(dict)


class ExpiredChallengeFactory(ChallengeFactory):
    """Factory for expired challenges."""

    start_date = factory.LazyFunction(lambda: timezone.now() - timedelta(days=14))
    end_date = factory.LazyFunction(lambda: timezone.now() - timedelta(days=7))
    status = Challenge.Status.COMPLETED


class FutureChallengeFactory(ChallengeFactory):
    """Factory for future challenges."""

    start_date = factory.LazyFunction(lambda: timezone.now() + timedelta(days=7))
    end_date = factory.LazyFunction(lambda: timezone.now() + timedelta(days=14))
    status = Challenge.Status.DRAFT


class UserChallengeFactory(DjangoModelFactory):
    """Factory for UserChallenge model."""

    class Meta:
        model = UserChallenge
        django_get_or_create = ("user", "challenge")

    user = factory.SubFactory(UserFactory)
    challenge = factory.SubFactory(ChallengeFactory)
    status = UserChallenge.Status.ENROLLED
    completed_at = None
    current_value = 0
    progress_data = factory.LazyFunction(dict)
    points_earned = 0
    badge_earned = False


class AchievementFactory(DjangoModelFactory):
    """Factory for Achievement model."""

    class Meta:
        model = Achievement
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Achievement {n}")
    slug = factory.Sequence(lambda n: f"achievement-{n}")
    description = factory.Faker("paragraph")
    achievement_type = Achievement.AchievementType.MILESTONE
    icon = "star"
    points_reward = 100
    badge = None
    criteria = factory.LazyFunction(dict)
    is_repeatable = False
    is_active = True
    order = factory.Sequence(lambda n: n)


class UserAchievementFactory(DjangoModelFactory):
    """Factory for UserAchievement model."""

    class Meta:
        model = UserAchievement
        django_get_or_create = ("user", "achievement")

    user = factory.SubFactory(UserFactory)
    achievement = factory.SubFactory(AchievementFactory)
    times_unlocked = 1
    metadata = factory.LazyFunction(dict)


class RewardFactory(DjangoModelFactory):
    """Factory for Reward model."""

    class Meta:
        model = Reward
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Reward {n}")
    slug = factory.Sequence(lambda n: f"reward-{n}")
    description = factory.Faker("paragraph")
    reward_type = Reward.RewardType.DIGITAL
    points_cost = 100
    quantity_available = None
    quantity_redeemed = 0
    is_active = True
    min_level = None
    valid_from = None
    valid_until = None
    metadata = factory.LazyFunction(dict)


class LimitedRewardFactory(RewardFactory):
    """Factory for limited quantity rewards."""

    quantity_available = 10
    quantity_redeemed = 0


class ExpiredRewardFactory(RewardFactory):
    """Factory for expired rewards."""

    valid_from = factory.LazyFunction(lambda: timezone.now() - timedelta(days=30))
    valid_until = factory.LazyFunction(lambda: timezone.now() - timedelta(days=1))


class FutureRewardFactory(RewardFactory):
    """Factory for future rewards."""

    valid_from = factory.LazyFunction(lambda: timezone.now() + timedelta(days=1))
    valid_until = factory.LazyFunction(lambda: timezone.now() + timedelta(days=30))


class RewardRedemptionFactory(DjangoModelFactory):
    """Factory for RewardRedemption model."""

    class Meta:
        model = RewardRedemption

    user = factory.SubFactory(UserFactory)
    reward = factory.SubFactory(RewardFactory)
    status = RewardRedemption.Status.PENDING
    points_spent = factory.LazyAttribute(lambda obj: obj.reward.points_cost)
    fulfilled_at = None
    fulfilled_by = None
    notes = ""
    metadata = factory.LazyFunction(dict)
