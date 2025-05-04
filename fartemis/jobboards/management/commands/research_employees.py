import logging
import traceback
from django.core.management.base import BaseCommand
from django.utils import timezone

from fartemis.companies.models import CompanyProfile
from fartemis.jobboards.models import Job
from fartemis.companies.controllers import EmployeeResearchController

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Research employees for a job posting'

    def add_arguments(self, parser):
        parser.add_argument(
            '--job_id',
            type=int,
            help='Job ID to research employees for (defaults to most recent job)',
            required=False
        )
        parser.add_argument(
            '--user_id',
            type=str,
            help='User ID to filter jobs by (required if job_id not provided)',
            required=False
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose output'
        )
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Enable debug mode with full traceback on errors'
        )

    def handle(self, *args, **options):
        job_id = options.get('job_id')
        user_id = options.get('user_id')
        verbose = options.get('verbose', False)
        debug = options.get('debug', False)
        
        # Configure logging
        if verbose:
            logging.basicConfig(level=logging.INFO)
        if debug:
            logging.basicConfig(level=logging.DEBUG)
        
        # Get the job
        job = None
        if job_id:
            try:
                job = Job.objects.get(id=job_id)
                self.stdout.write(self.style.SUCCESS(f"Found job: {job.title} at {job.company_name}"))
            except Job.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Job with ID {job_id} not found"))
                return
        else:
            # Need user_id to get the most recent job
            if not user_id:
                self.stdout.write(self.style.ERROR("Either job_id or user_id must be provided"))
                return
                
            # Get the most recent job for this user
            job = Job.objects.filter(user_id=user_id).order_by('-posted_date', '-id').first()
            if not job:
                self.stdout.write(self.style.ERROR(f"No jobs found for user {user_id}"))
                return
            self.stdout.write(self.style.SUCCESS(f"Using most recent job: {job.title} at {job.company_name}"))
        
        # Check if we have a company profile
        company_profile = job.company_profile
        if not company_profile:
            self.stdout.write(self.style.WARNING(f"No company profile found for {job.company_name}"))
            self.stdout.write("Creating a new company profile...")
            
            # Create a new company profile
            company_profile = CompanyProfile.objects.create(
                name=job.company_name,
                website=None  # We don't have this info yet
            )
            
            # Update the job with the new company profile
            job.company_profile = company_profile
            job.save()
            
            self.stdout.write(self.style.SUCCESS(f"Created company profile for {job.company_name}"))
        
        # Initialize the controller with proper exception handling
        self.stdout.write("Initializing employee research controller...")
        try:
            controller = EmployeeResearchController(
                company_profile=company_profile,
                job_id=job.id
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error initializing controller: {str(e)}"))
            if debug:
                traceback.print_exc()
            return
        
        # Start the research
        self.stdout.write("Starting employee research...")
        start_time = timezone.now()
        
        try:
            employees = controller.find_company_employees()
            
            # Display results
            duration = timezone.now() - start_time
            self.stdout.write(self.style.SUCCESS(
                f"Research completed in {duration.total_seconds():.2f} seconds"
            ))
            self.stdout.write(f"Found {len(employees)} potential contacts:")
            
            # Group employees by role
            roles = {}
            for user in employees:
                try:
                    association = user.company_associations.get(company=company_profile)
                    role_name = association.role.name if association.role else "Unknown"
                    
                    if role_name not in roles:
                        roles[role_name] = []
                    
                    # Check if we have contact methods
                    contact_methods = user.contact_methods.all()
                    contact_info = []
                    for method in contact_methods:
                        contact_info.append(f"{method.method_type.name}: {method.value}")
                    
                    roles[role_name].append({
                        'name': f"{user.first_name} {user.last_name}",
                        'title': association.job_title,
                        'influence': association.influence_level,
                        'contact': ", ".join(contact_info) if contact_info else "No contact info"
                    })
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"Error processing user {user.id}: {str(e)}"))
            
            # Display by role
            for role, people in roles.items():
                self.stdout.write(f"\n{role} ({len(people)}):")
                
                # Sort by influence level
                for person in sorted(people, key=lambda x: x['influence'], reverse=True):
                    self.stdout.write(f"  - {person['name']}: {person['title']} ({person['influence']}/10)")
                    self.stdout.write(f"    {person['contact']}")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error during research: {str(e)}"))
            if debug:
                traceback.print_exc()