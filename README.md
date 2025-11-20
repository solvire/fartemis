# Data Tactical  

## DTAC.io - Host for Fartemis Alpha

The gasseous ether from whence; the goddess agent of job hunting.

[![Built with Cookiecutter Django](https://img.shields.io/badge/built%20with-Cookiecutter%20Django-ff69b4.svg?logo=cookiecutter)](https://github.com/cookiecutter/cookiecutter-django/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

License: MIT

## Settings

Moved to [settings](https://cookiecutter-django.readthedocs.io/en/latest/1-getting-started/settings.html).

## Case Studies and Demos

Browse through some of the items we have chosen to showcase. Feedback or questions are welcome.

### 🧠 Therapy Session Analyzer

**AI-powered mental health documentation assistant**

Analyzes therapy sessions using NLP to identify CBT phases, therapeutic techniques, and conversation dynamics. This proof-of-concept demonstrates how AI can reduce documentation burden for mental health professionals while maintaining clinical standards and privacy.

[**→ View the Therapy Analyzer**](./scripts/nlp_case_study/)

**Key Features:**
- Speaker diarization (therapist vs. client identification)
- Automatic CBT phase classification
- Therapeutic technique detection
- Clinical quality metrics & visualizations
- 60-70% reduction in documentation time

**Technologies:** Python, AssemblyAI, pyannote.audio, Plotly, TextBlob


## Setup

### Local setup without docker on ubuntu


This is my flavor

Virtual env: 
    virtualenv -p python3.11 env
    . env/bin/activate

    pip install -r requirements/local.txt


### Set up the database

    CREATE ROLE fartemis WITH LOGIN PASSWORD 'your_secure_password';
    ALTER ROLE fartemis CREATEDB;  -- Allows creating databases (if needed)
    GRANT ALL PRIVILEGES ON DATABASE your_database TO fartemis;
    CREATE DATABASE fartemis OWNER fartemis;


### CSS - tailwind

I used the v0.dev service to create this template 

The below chat is the transcript of the actions

https://v0.dev/chat/dtac-software-development-landing-zZs3CsClWoK

Make sure to install tailwind if there are some discrepancies 

https://django-tailwind.readthedocs.io/en/latest/installation.html


## Basic Commands

### Pulling Jobs from LinkedIn

There is a command for pulling in jobs from linkedin. Below should get the data coming in. It will be stored in the FeedItem table. 

    ./manage.py linkedin_jobs --keywords "Python Engineer" --location "San Francisco"

### Find the geo_id from LinkedIn

Sometimes you will need or want to find the geo_id of the location. There is a search tool that will scrape the screen and pull that information out. 


    ./manage.py linkedin_geo_finder "Raleigh"

1. Raleigh, North Carolina, United States
   GeoID: 100197101
   Type: GEO

2. Raleigh-Durham-Chapel Hill Area
   GeoID: 90000664
   Type: GEO

... cont. 



### Setting Up Your Users

- To create a **normal user account**, just go to Sign Up and fill out the form. Once you submit it, you'll see a "Verify Your E-mail Address" page. Go to your console to see a simulated email verification message. Copy the link into your browser. Now the user's email should be verified and ready to go.

- To create a **superuser account**, use this command:

      $ python manage.py createsuperuser

For convenience, you can keep your normal user logged in on Chrome and your superuser logged in on Firefox (or similar), so that you can see how the site behaves for both kinds of users.

### Type checks

Running type checks with mypy:

    $ mypy fartemis

### Test coverage

To run the tests, check your test coverage, and generate an HTML coverage report:

    $ coverage run -m pytest
    $ coverage html
    $ open htmlcov/index.html

#### Running tests with pytest

    $ pytest

### Live reloading and Sass CSS compilation

Moved to [Live reloading and SASS compilation](https://cookiecutter-django.readthedocs.io/en/latest/2-local-development/developing-locally.html#using-webpack-or-gulp).

### Celery

This app comes with Celery.

To run a celery worker:

```bash
cd fartemis
celery -A config.celery_app worker -l info
```

Please note: For Celery's import magic to work, it is important _where_ the celery commands are run. If you are in the same folder with _manage.py_, you should be right.

To run [periodic tasks](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html), you'll need to start the celery beat scheduler service. You can start it as a standalone process:

```bash
cd fartemis
celery -A config.celery_app beat
```

or you can embed the beat service inside a worker with the `-B` option (not recommended for production use):

```bash
cd fartemis
celery -A config.celery_app worker -B -l info
```

### Sentry

Sentry is an error logging aggregator service. You can sign up for a free account at <https://sentry.io/signup/?code=cookiecutter> or download and host it yourself.
The system is set up with reasonable defaults, including 404 logging and integration with the WSGI application.

You must set the DSN url in production.

## Deployment

The following details how to deploy this application.

### Docker

See detailed [cookiecutter-django Docker documentation](https://cookiecutter-django.readthedocs.io/en/latest/3-deployment/deployment-with-docker.html).

