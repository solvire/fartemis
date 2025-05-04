"""
Usage Example:
./manage.py linkedin_jobs --keywords "Python Engineer" --location "San Francisco" --levels="mid-senior,director" --limit=50 --verbose
./manage.py linkedin_jobs --keywords "Data Scientist" --geo-id 103644278 --limit=30 # New York City Geo ID

Fetches jobs from LinkedIn using the voyager API via the linkedin_api library
and stores the raw job data (summary, details, skills) as FeedItem objects
for later processing. Requires LinkedIn credentials in Django settings.
"""
import time
import random
import logging
from datetime import datetime

from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone

# Third-party library for LinkedIn API
from linkedin_api import Linkedin

# Project models
from fartemis.jobboards.models import FeedSource, FeedItem # Removed JobSource as it wasn't used directly here
# Import the sanitization helper function
from fartemis.inherits.helpers import sanitize_unicode_nulls

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Fetch jobs from LinkedIn via Voyager API and store raw data as FeedItems'

    def add_arguments(self, parser):
        parser.add_argument('--keywords', type=str, default='Python Engineer',
                            help='Search keywords for jobs (e.g., "Software Engineer", "Product Manager")')
        parser.add_argument('--location', type=str,
                            help='Location name for job search (e.g., "London", "Remote", "United States")')
        parser.add_argument('--geo-id', type=str,
                            help='Optional: LinkedIn GeoID for precise location targeting (obtain via linkedin_geoid_finder command)')
        parser.add_argument('--limit', type=int, default=25,
                            help='Maximum number of job listings to fetch per search (LinkedIn may have its own limits)')
        parser.add_argument('--levels', type=str, default='4,5,6',
                            help='Comma-separated experience levels :param experience: A list of experience levels, one or many of "1", "2", "3", "4", "5" and "6" (internship, entry level, associate, mid-senior level, director and executive, respectively)')
        parser.add_argument('--verbose', action='store_true',
                            help='Display verbose output including partial job descriptions.')

    def handle(self, *args, **options):
        # Extract options
        keywords = options['keywords']
        location = options['location']
        geo_id = options['geo_id']
        limit = options['limit']
        levels = options['levels'].split(',') if options['levels'] else []
        verbose = options['verbose'] # Assign to local variable 'verbose'

        # Validate location requirement: Need either location name or geo_id
        if not location and not geo_id:
             self.stderr.write(self.style.ERROR("Please provide either --location or --geo-id."))
             return

        # Get linkedin feed source
        feed_source = self._get_linkedin_feed_source()
        if not feed_source:
            # Error message already printed in _get_linkedin_feed_source
            return

        # Get LinkedIn credentials
        username = getattr(settings, 'LINKEDIN_USERNAME', None)
        password = getattr(settings, 'LINKEDIN_PASSWORD', None)

        if not username or not password:
            self.stderr.write(self.style.ERROR('LINKEDIN_USERNAME and/or LINKEDIN_PASSWORD not found in Django settings.'))
            return

        self.stdout.write(self.style.SUCCESS(f'Attempting LinkedIn authentication as {username}...'))

        # Initialize the LinkedIn client
        try:
            # --- *** CORRECTED LINE *** ---
            # Use the local variable 'verbose' here
            api = Linkedin(username, password, debug=verbose)
            # --- *** END CORRECTION *** ---
            self.stdout.write(self.style.SUCCESS('Authentication successful!'))
        except Exception as e:
            logger.error(f"LinkedIn authentication failed: {e}", exc_info=True)
            self.stderr.write(self.style.ERROR(f'Authentication failed: {str(e)}'))
            return

        # Prepare filters for experience levels
        filters = self._prepare_experience_filters(levels)

        # Prepare search parameters
        search_params = {
            'keywords': keywords,
            'limit': limit,
            # Add location or geo_id preferentially
            'location_name': location if location else None, # Use location_name parameter if available
            'geo_id': [geo_id] if geo_id else None, # Expects a list
            # Include filters if they exist
            'filters': filters if filters else None
        }
        # Clean up None values from params as the library might expect absent keys
        search_params = {k: v for k, v in search_params.items() if v is not None}

        search_location_display = location or f"GeoID {geo_id}"
        self.stdout.write(f'Searching for "{keywords}" jobs in {search_location_display} (Limit: {limit}, Levels: {levels or "Any"})...')
        logger.info(f"LinkedIn search parameters: {search_params}")

        # Generate timestamp to group this search
        search_timestamp = timezone.now().isoformat() # Use ISO format for clarity
        jobs_found = 0
        jobs_processed = 0
        jobs_skipped = 0

        try:
            # Perform the job search using the linkedin_api library
            jobs = api.search_jobs(**search_params)

            if not jobs:
                self.stdout.write(self.style.WARNING('No jobs found matching the criteria.'))
                return

            jobs_found = len(jobs)
            self.stdout.write(self.style.SUCCESS(f'Found {jobs_found} matching job summaries.'))

            # Process and store each job summary and details
            for i, job_summary in enumerate(jobs, 1):
                job_id = None # Reset job_id for each iteration
                try:
                    # Extract job ID robustly
                    if 'jobPostingUrn' in job_summary:
                        job_id = job_summary['jobPostingUrn'].split(':')[-1]
                    elif 'entityUrn' in job_summary:
                         job_id = job_summary['entityUrn'].split(':')[-1]
                    elif 'jobId' in job_summary: # Fallback if structure changes
                         job_id = job_summary['jobId']

                    if not job_id:
                        logger.warning(f"Could not extract job ID from job summary #{i}. Data: {job_summary}")
                        self.stderr.write(self.style.WARNING(f'Skipping job summary #{i} - could not determine Job ID.'))
                        jobs_skipped += 1
                        continue

                    # Construct unique GUID
                    job_guid = f"linkedin_{job_id}"

                    # Check if this job FeedItem already exists
                    if FeedItem.objects.filter(guid=job_guid, source=feed_source).exists():
                        # Use the local 'verbose' variable for the condition
                        if verbose:
                            self.stdout.write(f'Job {job_id} (GUID: {job_guid}) already exists. Skipping...')
                        jobs_skipped += 1
                        continue

                    # Add random delay
                    sleep_time = random.uniform(1.5, 4.5)
                    # Use the local 'verbose' variable for the condition
                    if verbose:
                        self.stdout.write(f'Sleeping for {sleep_time:.2f} seconds before fetching details for job {job_id}...')
                    time.sleep(sleep_time)

                    # --- Fetching detailed data ---
                    self.stdout.write(f'Fetching details for job {i}/{jobs_found} (ID: {job_id})...')
                    details = api.get_job(job_id)

                    skills_data = None
                    skills = []
                    try:
                        skills_data = api.get_job_skills(job_id)
                        if skills_data and isinstance(skills_data, dict):
                            if 'skillMatchStatuses' in skills_data:
                                for skill_info in skills_data.get('skillMatchStatuses', []):
                                    skill_name = skill_info.get('skill', {}).get('name')
                                    if skill_name:
                                        skills.append(skill_name)
                            # Use the local 'verbose' variable for the condition
                            elif verbose:
                                logger.debug(f"Skills data for job {job_id} lacks 'skillMatchStatuses': {skills_data}")
                        elif skills_data:
                            logger.warning(f"Unexpected skills data format for job {job_id}: {type(skills_data)}")

                    except Exception as skills_err:
                        logger.warning(f"Error fetching/parsing skills for job {job_id}: {skills_err}", exc_info=False)
                        # Use the local 'verbose' variable for the condition
                        if verbose:
                             self.stderr.write(self.style.WARNING(f'Could not fetch skills for job {job_id}: {str(skills_err)}'))

                    # --- Create combined data object ---
                    combined_data = {
                        'job_summary': job_summary,
                        'job_details': details,
                        'skills_data': skills_data,
                        'extracted_skills': skills,
                        'query_metadata': {
                            'keywords': keywords,
                            'location_name': location,
                            'geo_id': geo_id,
                            'levels': levels,
                            'search_timestamp': search_timestamp,
                            'fetch_timestamp': timezone.now().isoformat()
                        }
                    }

                    # --- Sanitize Data ---
                    try:
                        sanitized_data = sanitize_unicode_nulls(combined_data)
                        # Use the local 'verbose' variable for the condition
                        if verbose:
                            logger.debug(f"Successfully sanitized data for job {job_id}")
                    except Exception as sanitize_err:
                         logger.error(f"Error sanitizing data for job {job_id}: {sanitize_err}", exc_info=True)
                         self.stderr.write(self.style.ERROR(f"Failed to sanitize data for job {i} ({job_id}). Skipping."))
                         jobs_skipped += 1
                         continue

                    # --- Create FeedItem ---
                    feed_item = FeedItem.objects.create(
                        guid=job_guid,
                        source=feed_source,
                        raw_data=sanitized_data,
                        is_processed=False,
                        fetched_at=timezone.now()
                    )
                    jobs_processed += 1

                    # --- Display Summary ---
                    title = details.get('title', 'Unknown Title')
                    company_details = details.get('companyDetails', {}).get('com.linkedin.voyager.jobs.JobPostingCompany', details.get('companyDetails', {}))
                    company = company_details.get('name', 'Unknown Company')
                    location_display = details.get('formattedLocation', 'Unknown Location')
                    remote = details.get('workRemoteAllowed', False)

                    self.stdout.write(self.style.SUCCESS(f"Saved job {i}: {title}"))
                    self.stdout.write(f"  Company: {company}")
                    self.stdout.write(f"  Location: {location_display} (Remote: {'Yes' if remote else 'No'})")
                    if skills:
                        self.stdout.write(f"  Skills: {', '.join(skills)}")

                    # Use the local 'verbose' variable for the condition
                    if verbose:
                        description_text = details.get('description', {}).get('text', 'No description available')
                        self.stdout.write("\n  Description:")
                        desc_limit = 500
                        display_desc = description_text[:desc_limit] + ('...' if len(description_text) > desc_limit else '')
                        self.stdout.write(f"    {display_desc}\n")

                except Exception as e:
                    job_id_display = job_id or f"summary #{i}"
                    self.stderr.write(self.style.ERROR(f'Error processing job {job_id_display}: {str(e)}'))
                    logger.error(f"Failed to process job {job_id_display}", exc_info=True)
                    jobs_skipped += 1
                    continue

            # --- Post-loop summary ---
            feed_source.last_fetched = timezone.now()
            feed_source.save(update_fields=['last_fetched'])
            self.stdout.write("-" * 30)
            self.stdout.write(self.style.SUCCESS(f'LinkedIn job fetch completed.'))
            self.stdout.write(f'  Total job summaries found: {jobs_found}')
            self.stdout.write(f'  New jobs saved to database: {jobs_processed}')
            self.stdout.write(f'  Jobs skipped (already exist or error): {jobs_skipped + (jobs_found - jobs_processed - jobs_skipped)}')

        except Exception as e:
            self.stderr.write(self.style.ERROR(f'An unexpected error occurred during job search: {str(e)}'))
            logger.error(f"Error during LinkedIn job search execution", exc_info=True)
            return
        


    def _get_linkedin_feed_source(self):
        """Gets or creates the LinkedIn FeedSource."""
        try:
            feed_source, created = FeedSource.objects.get_or_create(
                name='linkedin',
                defaults={
                    'description': 'Jobs fetched directly from LinkedIn Voyager API',
                    'url': 'https://www.linkedin.com/jobs/', # Placeholder URL
                    'source_type': 'api' # Or choose an appropriate type
                }
            )
            if created:
                 self.stdout.write(self.style.SUCCESS(f'Created LinkedIn FeedSource (ID: {feed_source.id})'))
            else:
                 self.stdout.write(f'Using existing LinkedIn FeedSource (ID: {feed_source.id})')
            return feed_source
        except Exception as e:
            logger.error(f"Failed to get or create LinkedIn FeedSource: {e}", exc_info=True)
            self.stderr.write(self.style.ERROR(f'Error accessing FeedSource model: {str(e)}'))
            return None


    def _prepare_experience_filters(self, levels):
        """Prepare LinkedIn API filters for experience levels.
           Maps common terms to LinkedIn API codes.
           Returns a dict suitable for the 'filters' parameter in search_jobs.
        """
        if not levels:
            return None # Return None if no levels specified

        # LinkedIn API uses specific codes for experience levels
        # Found via network inspection or library documentation
        experience_map = {
            'internship': '1',
            'entry': '2',
            'associate': '3',
            'mid-senior': '4', # Mid-Senior level
            'director': '5',
            'executive': '6'
        }

        # Map our level inputs to LinkedIn's expected values
        experience_codes = []
        for level in levels:
            level = level.lower().strip().replace('-', '') # Normalize keys

            if level in experience_map:
                experience_codes.append(experience_map[level])
            elif level == 'senior' or level == 'manager':
                # Map 'senior' and 'manager' to 'mid-senior' if not already added
                if experience_map['mid-senior'] not in experience_codes:
                    experience_codes.append(experience_map['mid-senior'])
            else:
                 self.stdout.write(self.style.WARNING(f"Unknown experience level '{level}' ignored."))

        if not experience_codes:
             return None # Return None if mapping results in empty list

        # Structure expected by linkedin_api library's search_jobs (check its source if unsure)
        # Common structure is {'experience': ['code1', 'code2']}
        return {'experience': experience_codes}
    
