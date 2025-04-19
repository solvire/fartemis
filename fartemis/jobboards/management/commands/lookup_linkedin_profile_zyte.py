"""
./manage.py lookup_linkedin_profile_zyte --first_name=Olivia --last_name=Melman --company="DigitalOcean"
./manage.py lookup_linkedin_profile_zyte --first_name=Olivia --last_name=Melman --company="DigitalOcean" --user_id=12345
"""
import logging
import uuid
from django.core.management.base import BaseCommand
from django.utils import timezone

from fartemis.companies.models import CompanyProfile
from fartemis.users.models import User, ContactMethodType, UserContactMethod, UserSourceLink
from fartemis.jobboards.clients import JobBoardClientFactory

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Look up a person on LinkedIn using Zyte API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--first_name',
            type=str,
            help='First name of the person to look up',
            required=True
        )
        parser.add_argument(
            '--last_name',
            type=str,
            help='Last name of the person to look up',
            required=True
        )
        parser.add_argument(
            '--company',
            type=str,
            help='Company name (optional)',
            required=False
        )
        parser.add_argument(
            '--user_id',
            type=str,
            help='User ID to update (if already exists)',
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
            help='Enable debug mode'
        )

    def handle(self, *args, **options):
        first_name = options.get('first_name')
        last_name = options.get('last_name')
        company_name = options.get('company')
        user_id = options.get('user_id')
        verbose = options.get('verbose', False)
        debug = options.get('debug', False)
        
        # Set up logging
        if verbose:
            logging.basicConfig(level=logging.INFO)
        if debug:
            logging.basicConfig(level=logging.DEBUG)
        
        self.stdout.write(f"Looking up LinkedIn profile for {first_name} {last_name}")
        
        # Get Zyte client
        try:
            zyte_client = JobBoardClientFactory.create('zyte')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error creating Zyte client: {str(e)}"))
            return
        
        # Look up profile
        try:
            profile_data = zyte_client.find_linkedin_profile(
                first_name=first_name,
                last_name=last_name,
                company_name=company_name
            )
            
            if not profile_data:
                self.stdout.write(self.style.WARNING(f"No LinkedIn profile found for {first_name} {last_name}"))
                return
                
            # Display profile information
            self.stdout.write(self.style.SUCCESS(f"Found LinkedIn profile: {profile_data.get('url')}"))
            self.stdout.write(f"Name: {profile_data.get('name')}")
            self.stdout.write(f"Title: {profile_data.get('title')}")
            self.stdout.write(f"Company: {profile_data.get('company')}")
            self.stdout.write(f"Handle: {profile_data.get('handle')}")
            
            # If user_id provided, update the user
            if user_id:
                try:
                    user = User.objects.get(id=user_id)
                    
                    # Update LinkedIn handle
                    user.linkedin_handle = profile_data.get('handle')
                    
                    # Check for name differences
                    if profile_data.get('name') and profile_data['name'] != f"{user.first_name} {user.last_name}":
                        # Store original name if it's different
                        original_name = f"{user.first_name} {user.last_name}"
                        
                        if not user.alternate_names:
                            user.alternate_names = []
                            
                        # Add to alternate names if not already there
                        if original_name not in user.alternate_names:
                            user.alternate_names.append(original_name)
                            
                        # Update name from profile
                        name_parts = profile_data['name'].split(' ', 1)
                        if len(name_parts) >= 2:
                            user.first_name = name_parts[0]
                            user.last_name = name_parts[1]
                            
                        self.stdout.write(self.style.SUCCESS(
                            f"Updated name from {original_name} to {profile_data['name']}"
                        ))
                    
                    # Save user
                    user.save()
                    
                    # Create LinkedIn contact method
                    linkedin_method_type, _ = ContactMethodType.objects.get_or_create(
                        name="LinkedIn Profile",
                        defaults={"category": "other"}
                    )
                    
                    UserContactMethod.objects.update_or_create(
                        user=user,
                        method_type=linkedin_method_type,
                        defaults={"value": profile_data.get('url')}
                    )
                    
                    # Create source link
                    UserSourceLink.objects.update_or_create(
                        user=user,
                        url=profile_data.get('url'),
                        defaults={
                            "source_type": "linkedin",
                            "title": f"LinkedIn: {profile_data.get('name')} - {profile_data.get('title')}",
                            "relevance_score": 1.0,
                            "notes": f"Found via Zyte lookup"
                        }
                    )
                    
                    self.stdout.write(self.style.SUCCESS(f"Updated user {user.id} with LinkedIn profile"))
                    
                except User.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f"User with ID {user_id} not found"))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error looking up LinkedIn profile: {str(e)}"))
            if debug:
                import traceback
                traceback.print_exc()