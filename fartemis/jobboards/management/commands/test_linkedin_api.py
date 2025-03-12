# File: fartemis/jobboards/management/commands/test_linkedin_api.py
"""
NOTE: does not work currently. Waiting on LinkedIn API access approval.


# Basic job search
python manage.py test_linkedin_api --query "python developer"

# More specific search
python manage.py test_linkedin_api --query "django developer" --location "San Francisco" --remote --level senior

# Get detailed job information
python manage.py test_linkedin_api --query "machine learning" --full

# Save results to database
python manage.py test_linkedin_api --query "data scientist" --save

# Debug mode to see API responses
python manage.py test_linkedin_api --query "software engineer" --debug

# Get specific job details
python manage.py test_linkedin_api --job-id "3634446281"
"""
import json
import sys
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone

from jobboards.clients import LinkedInClient
from jobboards.constants import JobLevel, EmploymentType


class Command(BaseCommand):
    help = 'Test LinkedIn API integration for job search'

    def add_arguments(self, parser):
        parser.add_argument('--query', type=str, help='Job search query (e.g. "python developer")')
        parser.add_argument('--location', type=str, help='Job location (e.g. "San Francisco, CA")')
        parser.add_argument('--remote', action='store_true', help='Search for remote positions only')
        parser.add_argument('--level', type=str, choices=[level[0] for level in JobLevel.CHOICES], 
                          help='Job seniority level')
        parser.add_argument('--employment-type', type=str, 
                          choices=[et[0] for et in EmploymentType.CHOICES],
                          help='Employment type')
        parser.add_argument('--limit', type=int, default=10, help='Maximum number of results to display')
        parser.add_argument('--full', action='store_true', help='Show full job details, including description')
        parser.add_argument('--save', action='store_true', help='Save job results to the database')
        parser.add_argument('--job-id', type=str, help='Get details for a specific job ID')
        parser.add_argument('--debug', action='store_true', help='Show debug information including raw API responses')

    def handle(self, *args, **options):
        self.debug = options['debug']
        
        try:
            # Initialize the LinkedIn client
            self.stdout.write(self.style.NOTICE('Initializing LinkedIn client...'))
            client = LinkedInClient(
                api_key=settings.LINKEDIN_API_KEY,
                base_url=settings.LINKEDIN_API_BASE_URL
            )
            
            # Check if we're getting a specific job by ID
            if options['job_id']:
                self._get_job_by_id(client, options['job_id'], options['full'])
                return
                
            # Validate search parameters
            if not options['query']:
                raise CommandError('You must provide a search query with --query')
                
            # Perform the search
            self.stdout.write(self.style.NOTICE(f"Searching for: {options['query']}"))
            
            results = client.search_jobs(
                query=options['query'],
                location=options['location'] or '',
                remote=options['remote'],
                job_level=options['level'] or '',
                employment_type=options['employment_type'] or '',
            )
            
            if self.debug:
                self.stdout.write(self.style.NOTICE('Raw API response:'))
                self.stdout.write(json.dumps(results, indent=2)[:1000] + '...')
                
            # Limit results based on the --limit parameter
            results = results[:options['limit']]
            
            # Display results
            if not results:
                self.stdout.write(self.style.WARNING('No jobs found matching your criteria.'))
                return
                
            self.stdout.write(self.style.SUCCESS(f'Found {len(results)} jobs:'))
            self._display_results(results, options['full'])
            
            # Save to database if requested
            if options['save']:
                self._save_results(results)
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))
            if self.debug:
                import traceback
                self.stdout.write(self.style.ERROR(traceback.format_exc()))
            sys.exit(1)

    def _get_job_by_id(self, client, job_id, full=False):
        """Get and display details for a specific job ID"""
        self.stdout.write(self.style.NOTICE(f'Getting details for job ID: {job_id}'))
        
        try:
            job_details = client.get_job_details(job_id)
            
            if self.debug:
                self.stdout.write(self.style.NOTICE('Raw API response:'))
                self.stdout.write(json.dumps(job_details, indent=2))
                
            self.stdout.write(self.style.SUCCESS('Job details:'))
            self._display_job(job_details, full)
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error getting job details: {str(e)}'))
            if self.debug:
                import traceback
                self.stdout.write(self.style.ERROR(traceback.format_exc()))
    
    def _display_results(self, results, full=False):
        """Display job search results in a formatted way"""
        for i, job in enumerate(results, 1):
            self.stdout.write(f"\n{i}. {self.style.SUCCESS(job['title'])}")
            self._display_job(job, full)
    
    def _display_job(self, job, full=False):
        """Display a single job in a formatted way"""
        self.stdout.write(f"   Company: {job['company']}")
        self.stdout.write(f"   Location: {job['location']} {'(Remote)' if job.get('remote') else ''}")
        
        # Display salary information if available
        if job.get('salary_min') or job.get('salary_max'):
            salary_range = []
            if job.get('salary_min'):
                salary_range.append(f"${job['salary_min']:,}")
            if job.get('salary_max'):
                salary_range.append(f"${job['salary_max']:,}")
            self.stdout.write(f"   Salary: {' - '.join(salary_range)} {job.get('salary_currency', 'USD')}")
        
        # Display employment type and level if available
        if job.get('employment_type'):
            self.stdout.write(f"   Type: {job['employment_type']}")
        if job.get('job_level'):
            self.stdout.write(f"   Level: {job['job_level']}")
        
        # Display posted date if available
        if job.get('posted_date'):
            posted_date = job['posted_date']
            if not isinstance(posted_date, str):
                posted_date = posted_date.strftime('%Y-%m-%d')
            self.stdout.write(f"   Posted: {posted_date}")
        
        self.stdout.write(f"   URL: {job['url']}")
        
        # Display full description if requested
        if full and job.get('description'):
            self.stdout.write("\n   Description:")
            # Limit to a reasonable length for display
            desc = job['description']
            if len(desc) > 1000:
                desc = desc[:1000] + "... (truncated)"
            for line in desc.split('\n'):
                self.stdout.write(f"     {line}")
    
    def _save_results(self, results):
        """Save job results to the database"""
        from django.contrib.auth import get_user_model
        from jobboards.models import Job
        
        User = get_user_model()
        
        # Get the first superuser for testing purposes
        user = User.objects.filter(is_superuser=True).first()
        if not user:
            self.stdout.write(self.style.ERROR('No superuser found. Please create a superuser to save jobs.'))
            return
            
        saved_count = 0
        for job_data in results:
            try:
                # Use update_or_create to avoid duplicates
                job, created = Job.objects.update_or_create(
                    source='linkedin',
                    source_id=job_data['id'],
                    user=user,
                    defaults={
                        'title': job_data['title'],
                        'company_name': job_data['company'],
                        'location': job_data['location'],
                        'remote': job_data.get('remote', False),
                        'description': job_data.get('description', ''),
                        'description_html': job_data.get('description_html', ''),
                        'url': job_data['url'],
                        'posted_date': job_data.get('posted_date'),
                        'salary_min': job_data.get('salary_min'),
                        'salary_max': job_data.get('salary_max'),
                        'salary_currency': job_data.get('salary_currency', 'USD'),
                        'employment_type': job_data.get('employment_type', ''),
                        'job_level': job_data.get('job_level', ''),
                    }
                )
                
                # Try to link or create a company profile
                job.link_or_create_company_profile()
                
                saved_count += 1
                
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Error saving job '{job_data['title']}': {str(e)}"))
                continue
                
        self.stdout.write(self.style.SUCCESS(f'Successfully saved {saved_count} jobs to the database.'))