"""
./manage.py lookup_linkedin_profile --first_name=Olivia --last_name=Melman --company="DigitalOcean"
./manage.py lookup_linkedin_profile --first_name=Olivia --last_name=Melman --company="DigitalOcean" --user_id=12345

"""

import logging
from django.core.management.base import BaseCommand
from django.utils import timezone

from fartemis.companies.models import CompanyProfile
from fartemis.users.models import User, ContactMethodType, UserContactMethod, UserSourceLink
from fartemis.companies.controllers import LinkedInProfileFinder

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Look up a person\'s LinkedIn profile'

    def add_arguments(self, parser):
        parser.add_argument(
            '--first_name',
            type=str,
            help='First name of the person to search for',
            required=True
        )
        parser.add_argument(
            '--last_name',
            type=str,
            help='Last name of the person to search for',
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
            help='User ID to update with found profile',
            required=False
        )
        parser.add_argument(
            '--search_engine',
            type=str,
            choices=['duckduckgo', 'tavily', 'both'],
            default='both',
            help='Search engine to use'
        )
        parser.add_argument(
            '--max_pages',
            type=int,
            help='Maximum number of pages to check',
            default=5
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose output'
        )

    def handle(self, *args, **options):
        first_name = options['first_name']
        last_name = options['last_name']
        company = options.get('company', '')
        user_id = options.get('user_id')
        search_engine = options.get('search_engine', 'both')
        max_pages = options.get('max_pages', 5)
        verbose = options.get('verbose', False)
        
        self.stdout.write(f"Looking up LinkedIn profile for {first_name} {last_name}")
        if company:
            self.stdout.write(f"Company context: {company}")
        
        # Initialize the profile finder
        finder = LinkedInProfileFinder(verbose=verbose)
        
        # Find the profile
        profile_info = finder.find_profile(
            first_name=first_name,
            last_name=last_name,
            company=company,
            search_engine=search_engine,
            max_pages=max_pages
        )
        
        if not profile_info:
            self.stdout.write(self.style.ERROR("No LinkedIn profile found"))
            return None
        
        # Display profile information
        self.stdout.write(self.style.SUCCESS(f"Found LinkedIn profile:"))
        self.stdout.write(f"URL: {profile_info['url']}")
        self.stdout.write(f"Handle: {profile_info['handle']}")
        self.stdout.write(f"Confidence: {profile_info['confidence']}")
        
        # If a user_id was provided, update the user record
        if user_id:
            try:
                user = User.objects.get(id=user_id)
                
                # Update LinkedIn handle
                old_handle = user.linkedin_handle
                user.linkedin_handle = profile_info['handle']
                
                # Check for potential name change
                if self._might_be_name_change(profile_info['handle'], first_name, last_name):
                    # Store original name in alternate_names if not already there
                    if not user.alternate_names:
                        user.alternate_names = []
                        
                    original_name = f"{first_name} {last_name}"
                    if original_name not in user.alternate_names:
                        user.alternate_names.append(original_name)
                        self.stdout.write(self.style.WARNING(
                            f"Handle suggests possible name change. Added '{original_name}' to alternate names."
                        ))
                
                # Create LinkedIn contact method
                linkedin_method_type, _ = ContactMethodType.objects.get_or_create(
                    name="LinkedIn Profile",
                    defaults={"category": "other"}
                )
                
                contact_method, created = UserContactMethod.objects.update_or_create(
                    user=user,
                    method_type=linkedin_method_type,
                    defaults={"value": profile_info['url']}
                )
                
                # Create source link
                source_link, created = UserSourceLink.objects.update_or_create(
                    user=user,
                    url=profile_info['url'],
                    defaults={
                        "source_type": "linkedin",
                        "title": f"LinkedIn Profile: {profile_info['handle']}",
                        "relevance_score": float(profile_info['match_score']) / 20.0,  # Normalize to 0-1 range
                        "notes": f"Found via LinkedIn profile search"
                    }
                )
                
                user.save()
                
                self.stdout.write(self.style.SUCCESS(f"Updated user {user.id} with LinkedIn handle"))
                if old_handle and old_handle != profile_info['handle']:
                    self.stdout.write(f"Previous handle: {old_handle}")
                
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"User with ID {user_id} not found"))
        
        return profile_info['handle']
    
    def _might_be_name_change(self, handle, first_name, last_name):
        """
        Check if a LinkedIn handle suggests a name change
        
        Args:
            handle: LinkedIn handle
            first_name: First name we know
            last_name: Last name we know
            
        Returns:
            bool: True if might be a name change, False otherwise
        """
        handle_lower = handle.lower()
        first_lower = first_name.lower()
        last_lower = last_name.lower()
        
        # Direct match - not a name change
        if handle_lower == f"{first_lower}{last_lower}" or handle_lower == f"{last_lower}{first_lower}":
            return False
            
        # Common variations - not a name change
        variations = [
            f"{first_lower}.{last_lower}",
            f"{first_lower}-{last_lower}",
            f"{first_lower}_{last_lower}",
            f"iam{first_lower}{last_lower}",
            f"{first_lower[0]}{last_lower}",
            f"{first_lower}{last_lower[0]}"
        ]
        
        if any(variation in handle_lower for variation in variations):
            return False
            
        # If first name is in handle but last name is not, might be a name change
        if first_lower in handle_lower and last_lower not in handle_lower:
            return True
            
        # If neither name component is in the handle, might be a name change
        if first_lower not in handle_lower and last_lower not in handle_lower:
            return True
            
        return False