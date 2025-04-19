"""
# To process a single user
python manage.py find_linkedin_profiles --user_id=abc123

# To process all users for a company
python manage.py find_linkedin_profiles --company_id=42

# To force update even if LinkedIn handle exists
python manage.py find_linkedin_profiles --company_id=42 --force
"""
import logging
import traceback
import uuid
from django.core.management.base import BaseCommand
from django.utils import timezone

from fartemis.companies.models import CompanyProfile, UserSourceLink
from fartemis.users.models import User, ContactMethodType, UserContactMethod
from fartemis.companies.controllers import EmployeeResearchController

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Find LinkedIn profiles for users in the system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user_id',
            type=str,
            help='Specific user ID to lookup LinkedIn profile for',
            required=False
        )
        parser.add_argument(
            '--company_id',
            type=int,
            help='Company ID to lookup profiles for all employees',
            required=False
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Update even if LinkedIn handle already exists'
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
        user_id = options.get('user_id')
        company_id = options.get('company_id')
        force_update = options.get('force', False)
        verbose = options.get('verbose', False)
        debug = options.get('debug', False)
        
        # Configure logging
        if verbose:
            logging.basicConfig(level=logging.INFO)
        if debug:
            logging.basicConfig(level=logging.DEBUG)
        
        # We need either a user_id or company_id
        if not user_id and not company_id:
            self.stdout.write(self.style.ERROR("Either user_id or company_id must be provided"))
            return
        
        # Get users to process
        users_to_process = []
        
        if user_id:
            try:
                user = User.objects.get(id=user_id)
                users_to_process.append(user)
                self.stdout.write(self.style.SUCCESS(f"Found user: {user.first_name} {user.last_name}"))
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"User with ID {user_id} not found"))
                return
        elif company_id:
            try:
                company = CompanyProfile.objects.get(id=company_id)
                self.stdout.write(self.style.SUCCESS(f"Found company: {company.name}"))
                
                # Get all users associated with this company
                associations = company.personnel.all()
                for association in associations:
                    # Skip users who already have LinkedIn handles unless force update
                    if not force_update and association.user.linkedin_handle:
                        continue
                    users_to_process.append(association.user)
                
                self.stdout.write(f"Found {len(users_to_process)} users to process")
                
            except CompanyProfile.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Company with ID {company_id} not found"))
                return
        
        # Process users
        processed_count = 0
        updated_count = 0
        
        for user in users_to_process:
            self.stdout.write(f"Processing: {user.first_name} {user.last_name}")
            processed_count += 1
            
            # Skip if user already has LinkedIn handle and we're not forcing update
            if user.linkedin_handle and not force_update:
                self.stdout.write(f"  Skipping: Already has LinkedIn handle ({user.linkedin_handle})")
                continue
            
            # Get company for this user
            company = None
            try:
                association = user.company_associations.first()
                if association:
                    company = association.company
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  Error getting company: {str(e)}"))
                if debug:
                    traceback.print_exc()
                continue
            
            if not company:
                self.stdout.write(self.style.WARNING(f"  No company associated with user"))
                continue
                
            # Initialize controller
            try:
                controller = EmployeeResearchController(company_profile=company)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  Error initializing controller: {str(e)}"))
                if debug:
                    traceback.print_exc()
                continue
                
            # Search for LinkedIn profile
            try:
                self.stdout.write(f"  Searching for LinkedIn profile...")
                linkedin_data = controller.find_linkedin_profile(
                    user.first_name, 
                    user.last_name,
                    company.name
                )
                
                if not linkedin_data:
                    self.stdout.write(self.style.WARNING(f"  No LinkedIn profile found"))
                    continue
                    
                # Update user with LinkedIn data
                linkedin_url = linkedin_data.get("url")
                
                if linkedin_url:
                    # Extract LinkedIn handle
                    linkedin_handle = linkedin_url.split("/in/")[-1].rstrip("/")
                    user.linkedin_handle = linkedin_handle
                    
                    # Create or update LinkedIn contact method
                    linkedin_method_type, _ = ContactMethodType.objects.get_or_create(
                        name="LinkedIn Profile",
                        defaults={"category": "other"}
                    )
                    
                    contact_method, created = UserContactMethod.objects.update_or_create(
                        user=user,
                        method_type=linkedin_method_type,
                        defaults={"value": linkedin_url}
                    )
                    
                    # Create source link
                    source_link, created = UserSourceLink.objects.get_or_create(
                        user=user,
                        url=linkedin_url,
                        defaults={
                            "source_type": "linkedin",
                            "title": linkedin_data.get("title", "LinkedIn Profile"),
                            "relevance_score": 1.0,
                            "notes": f"Found via search: {linkedin_data.get('source', 'unknown')}"
                        }
                    )
                    
                    # Check for name changes
                    name_change = linkedin_data.get("name_change")
                    if name_change:
                        current_name = name_change.get("current_name")
                        if current_name:
                            # Store original name in alternate_names
                            original_name = f"{user.first_name} {user.last_name}"
                            
                            if not user.alternate_names:
                                user.alternate_names = []
                                
                            if original_name not in user.alternate_names:
                                user.alternate_names.append(original_name)
                            
                            # Update name to current name
                            name_parts = current_name.split()
                            if len(name_parts) >= 2:
                                user.first_name = name_parts[0]
                                user.last_name = " ".join(name_parts[1:])
                                
                                self.stdout.write(self.style.SUCCESS(
                                    f"  Updated name from {original_name} to {current_name}"
                                ))
                    
                    # Save user
                    user.save()
                    updated_count += 1
                    
                    self.stdout.write(self.style.SUCCESS(
                        f"  Updated LinkedIn profile: {linkedin_url}"
                    ))
                    
                    # If we found any additional links, store them too
                    if "additional_links" in linkedin_data:
                        for link_data in linkedin_data.get("additional_links", []):
                            link_url = link_data.get("url")
                            if link_url:
                                source_link, created = UserSourceLink.objects.get_or_create(
                                    user=user,
                                    url=link_url,
                                    defaults={
                                        "source_type": link_data.get("type", "other"),
                                        "title": link_data.get("title", "Related Link"),
                                        "relevance_score": link_data.get("confidence", 0.5),
                                        "notes": f"Found via LinkedIn search"
                                    }
                                )
                                
                                if created:
                                    self.stdout.write(f"  Added source link: {link_url}")
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  Error updating user: {str(e)}"))
                if debug:
                    traceback.print_exc()
        
        # Show summary
        self.stdout.write(self.style.SUCCESS(
            f"\nProcessed {processed_count} users, updated {updated_count} LinkedIn profiles"
        ))