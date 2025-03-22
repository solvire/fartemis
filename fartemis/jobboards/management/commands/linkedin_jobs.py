"""
./manage.py linkedin_jobs --keywords "Python Engineer" --location "San Francisco"
"""
import time
import random
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
import logging
from datetime import datetime
from linkedin_api import Linkedin
from fartemis.jobboards.models import FeedSource, FeedItem, JobSource

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Fetch jobs from LinkedIn and store them directly as feed items'

    def add_arguments(self, parser):
        parser.add_argument('--keywords', type=str, default='Python Engineer', 
                            help='Search keywords')
        parser.add_argument('--geo-id', type=str,
                            help='LinkedIn GeoID (obtained from linkedin_geoid_finder command)')
        parser.add_argument('--location', type=str,
                            help='Location for job')
        parser.add_argument('--limit', type=int, default=25, 
                            help='Number of results to fetch')
        parser.add_argument('--levels', type=str, default='senior,manager,director', 
                            help='Experience levels (comma separated)')
        parser.add_argument('--verbose', action='store_true', 
                            help='Display full job descriptions')

    def handle(self, *args, **options):
        # Extract options
        keywords = options['keywords']
        geo_id = options['geo_id']
        location = options['location']
        limit = options['limit']
        levels = options['levels'].split(',') if options['levels'] else []
        verbose = options['verbose']

        # Get linkedin feed source
        feed_source = self._get_linkedin_feed_source()
        if not feed_source:
            self.stderr.write(self.style.ERROR('LinkedIn feed source not found. Check that a FeedSource with name "linkedin" exists.'))
            return

        # Get LinkedIn credentials
        username = getattr(settings, 'LINKEDIN_USERNAME', None)
        password = getattr(settings, 'LINKEDIN_PASSWORD', None)

        if not username or not password:
            self.stderr.write(self.style.ERROR('LinkedIn credentials not found in settings'))
            return

        self.stdout.write(self.style.SUCCESS(f'Authenticating with LinkedIn as {username}...'))
        
        # Initialize the LinkedIn client
        try:
            api = Linkedin(username, password)
            self.stdout.write(self.style.SUCCESS('Authentication successful!'))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Authentication failed: {str(e)}'))
            return

        # Prepare filters for experience levels
        filters = self._prepare_experience_filters(levels)

        # Search for jobs
        search_params = {
            'keywords': keywords,
            'location': location,
            'limit': limit
        }
        
        if geo_id:
            search_params['geo_id'] = geo_id
        
        if filters:
            search_params['filters'] = filters

        self.stdout.write(f'Searching for "{keywords}" jobs in {location} (limit: {limit})...')
        
        # Generate timestamp to group this search
        search_timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        jobs_found = 0
        jobs_processed = 0
        
        try:
            # Search with parameters
            jobs = api.search_jobs(**search_params)
            
            if not jobs:
                self.stdout.write(self.style.WARNING('No jobs found matching the criteria'))
                return
                
            jobs_found = len(jobs)
            self.stdout.write(self.style.SUCCESS(f'Found {jobs_found} matching jobs'))
            
            # Process and store each job
            for i, job in enumerate(jobs, 1):
                try:
                    # Extract job ID from entityUrn
                    job_id = job.get('jobId', job.get('entityUrn', '').split(':')[-1])

                    # take a random nap to obscure detection
                    self.stdout.write(f'Sleeping for a random time...')
                    time.sleep(random.randint(1, 5))

                    job_guid = f"{feed_source.name}_{job_id}"
                    
                    if not job_id:
                        self.stderr.write(f'Could not extract job ID from job {i}')
                        continue
                    
                    # Check if this job is already in the database
                    existing_item = FeedItem.objects.filter(
                        source=feed_source,
                        guid=job_guid
                    ).first()
                    
                    if existing_item:
                        self.stdout.write(f'Job {job_id} already exists in database, skipping...')
                        continue
                    
                    # Get detailed job information
                    self.stdout.write(f'Fetching details for job {i} (ID: {job_id})...')
                    details = api.get_job(job_id)
                    
                    # Try to get skills (may fail if API limitations or changes)
                    skills_data = None
                    skills = []
                    try:
                        skills_data = api.get_job_skills(job_id)
                        if skills_data and isinstance(skills_data, dict) and 'skillMatchStatuses' in skills_data:
                            for skill_data in skills_data.get('skillMatchStatuses', []):
                                skill_name = skill_data.get('skill', {}).get('name', '')
                                if skill_name:
                                    skills.append(skill_name)
                    except Exception as e:
                        self.stderr.write(f'Error fetching skills for job {job_id}: {str(e)}')
                    
                    # Create combined data object with all information
                    combined_data = {
                        'job_summary': job,
                        'job_details': details,
                        'skills_data': skills_data,
                        'extracted_skills': skills,
                        'query_metadata': {
                            'keywords': keywords,
                            'location': location,
                            'geo_id': geo_id,
                            'timestamp': search_timestamp,
                            'levels': levels,
                            'search_id': search_timestamp
                        }
                    }
                    
                    # Create FeedItem to store the data
                    feed_item = FeedItem.objects.create(
                        guid=job_guid,
                        source=feed_source,
                        raw_data=combined_data,
                        is_processed=False
                    )
                    
                    jobs_processed += 1
                    
                    # Display brief summary
                    title = details.get('title', 'Unknown Title')
                    company = details.get('companyDetails', {}).get('name', 'Unknown Company')
                    location = details.get('formattedLocation', 'Unknown Location')
                    remote = details.get('workRemoteAllowed', False)
                    
                    self.stdout.write(self.style.SUCCESS(f"Saved job {i}: {title}"))
                    self.stdout.write(f"Company: {company}")
                    self.stdout.write(f"Location: {location} (Remote: {'Yes' if remote else 'No'})")
                    self.stdout.write(f"Skills: {', '.join(skills)}")
                    
                    if verbose:
                        description_text = details.get('description', {}).get('text', 'No description available')
                        self.stdout.write("\nDescription:")
                        # Truncate long descriptions for display
                        if len(description_text) > 300:
                            self.stdout.write(description_text[:300] + "...")
                        else:
                            self.stdout.write(description_text)
                        
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f'Error processing job {i}: {str(e)}'))
                    continue
            
            # Update feed source last_fetched time
            feed_source.last_fetched = timezone.now()
            feed_source.save(update_fields=['last_fetched'])
            
            # Summary
            self.stdout.write(self.style.SUCCESS(
                f'LinkedIn job fetch completed: Found {jobs_found} jobs, saved {jobs_processed} new jobs to database'
            ))
            
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error searching jobs: {str(e)}'))
            return
            
    def _get_linkedin_feed_source(self):
        """Get the LinkedIn feed source."""
        try:
            feed_source = FeedSource.objects.get(name='linkedin')
            self.stdout.write(f'Using LinkedIn feed source (ID: {feed_source.id})')
            return feed_source
        except FeedSource.DoesNotExist:
            self.stderr.write(self.style.ERROR('LinkedIn feed source not found. Please create a FeedSource with name "linkedin".'))
            return None
            
    def _prepare_experience_filters(self, levels):
        """Prepare LinkedIn API filters for experience levels."""
        if not levels:
            return {}
            
        # LinkedIn API uses specific codes for experience levels
        experience_map = {
            'internship': 1,
            'entry': 2, 
            'associate': 3,
            'mid-senior': 4,  # Both 'senior' and 'manager' map here
            'director': 5,
            'executive': 6
        }
        
        # Map our level inputs to LinkedIn's expected values
        experience_codes = []
        for level in levels:
            level = level.lower().strip()
            if level in experience_map:
                experience_codes.append(experience_map[level])
            elif level == 'senior' or level == 'manager':  
                # Special case for 'senior' and 'manager' which map to 'mid-senior'
                experience_codes.append(experience_map['mid-senior'])
        
        return {'experience': experience_codes} if experience_codes else {}