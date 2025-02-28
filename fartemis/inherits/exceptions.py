"""
Base exceptions files for Meditrina
SS: 2022-04-19
"""

from rest_framework.exceptions import ValidationError


class BaseValidationError(ValidationError):
    pass
