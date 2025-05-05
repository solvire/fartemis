#!/usr/bin/env python
import os
import sys
from pathlib import Path

import environ

if __name__ == "__main__":
    ROOT_DIR = environ.Path()  # (pearl/config/settings/base.py - 3 = pearl/)
    env = environ.Env()

    # .env file
    READ_DOT_ENV_FILE = os.path.isfile(str(ROOT_DIR.path(".env")))

    if READ_DOT_ENV_FILE:
        # Operating System Environment variables have precedence over variables defined in the .env file,
        # that is to say variables from the .env files will only be used if not defined
        # as environment variables.
        env_file = str(ROOT_DIR.path(".env"))
        env.read_env(env_file)
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", env("DJANGO_SETTINGS_MODULE"))
    else:
        print(".env missing using ENV for module settings")
        os.environ.setdefault(
            "DJANGO_SETTINGS_MODULE",
            env("DJANGO_SETTINGS_MODULE", default="config.settings.local"),
        )
        # os.environ.setdefault("DJANGO_SETTINGS_MODULE", DJANGO_SETTINGS_MODULE)

    try:
        from django.core.management import execute_from_command_line
    except ImportError:
        # The above import may fail for some other reason. Ensure that the
        # issue is really that Django is missing to avoid masking other
        # exceptions on Python 2.
        try:
            import django  # noqa
        except ImportError:
            raise ImportError(
                "Couldn't import Django. Are you sure it's installed and "
                "available on your PYTHONPATH environment variable? Did you "
                "forget to activate a virtual environment?"
            )

        raise

    # This allows easy placement of apps within the interior
    # drakkar directory.
    current_path = Path(__file__).parent.resolve()
    sys.path.append(str(current_path / "fartemis"))

    execute_from_command_line(sys.argv)
