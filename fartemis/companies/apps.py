import contextlib

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CompaniesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'fartemis.companies'  # Full import path
    label = 'companies'  # Short name for app_label
    verbose_name = 'Companies'