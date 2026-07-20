from django import template

from apps.accounts.services import PasswordService

register = template.Library()


@register.simple_tag
def default_password(user):
    """Return the parameterized default password for a user.

    Delegates to `PasswordService.generate_password()` — the single source
    of truth for the password formula (issue #58, 3rd recurrence: this
    templatetag had its own inline copy of the formula, using lowercase +
    'x' padding instead of PasswordService's uppercase + 'X' padding, so the
    password shown in the "eye" column of the user list never matched the
    real, usable login password).
    """
    return PasswordService.generate_password(user.document_number, user.first_name)
