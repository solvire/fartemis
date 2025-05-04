"""
Usage Examples:

1. Lookup by User ID (updates the user record):
   ./manage.py lookup_linkedin_profile --user_id=your_user_uuid_here
   ./manage.py lookup_linkedin_profile --user_id=your_user_uuid_here --company="Context Company Inc" # Optional company context
   ./manage.py lookup_linkedin_profile --user_id=your_user_uuid_here --force # Overwrites existing handle

2. Lookup by Name and Required Company (prints results only):
   ./manage.py lookup_linkedin_profile --first_name=Olivia --last_name=Melman --company="DigitalOcean"

Common options (can be combined with any mode):
   --search_engine=duckduckgo  (default: both)
   --max_pages=3             (default: 5)
   --verbose

"""
import logging
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.conf import settings # Import settings if User model is from settings.AUTH_USER_MODEL

# Assuming models are correctly imported from your app structure
from fartemis.users.models import User, ContactMethodType, UserContactMethod, UserSourceLink, UserCompanyAssociation # Added UserCompanyAssociation
from fartemis.companies.models import CompanyProfile # Needed if fetching company from association
from fartemis.companies.controllers import LinkedInProfileFinder

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    # Keep help text updated
    help = 'Looks up a LinkedIn profile. Requires company context. Provide --user_id OR --first_name/--last_name. The --company argument is required if NOT using --user_id, and optional (but recommended for clarity) if using --user_id.'

    def add_arguments(self, parser):
        # --- Primary Identifier ---
        parser.add_argument(
            '--user_id',
            type=str,
            help='(Primary Mode) UUID of the User to look up and update. If provided, first/last name arguments are ignored for lookup. Company context will be inferred or taken from --company.'
        )

        # --- Name/Company Based Lookup (Alternative Mode) ---
        parser.add_argument(
            '--first_name',
            type=str,
            help='First name to search for. Required if --user_id is NOT provided.'
        )
        parser.add_argument(
            '--last_name',
            type=str,
            help='Last name to search for. Required if --user_id is NOT provided.'
        )
        # --- Company is now ALWAYS required contextually ---
        parser.add_argument(
            '--company',
            type=str,
            # Now conditionally required: required if NOT using --user_id.
            # If using --user_id, it's optional override/clarification.
            help='Company name context. *Required* if --user_id is NOT provided. If --user_id IS provided, this overrides inferred company or clarifies multiple associations.'
        )

        # --- Search Configuration ---
        parser.add_argument('--search_engine', type=str, choices=['duckduckgo', 'tavily', 'both'], default='both', help='Search engine to use (default: both).')
        parser.add_argument('--max_pages', type=int, default=5, help='Maximum number of search result pages to check (default: 5).')
        parser.add_argument('--verbose', action='store_true', help='Enable verbose output.')
        parser.add_argument('--force', action='store_true', help='Force lookup and update even if user already has a LinkedIn handle (applies only when using --user_id).')

    def handle(self, *args, **options):
        self.verbose = options.get('verbose', False)
        self.finder = LinkedInProfileFinder(verbose=self.verbose)
        self.options = options

        user_id = options.get('user_id')
        company_arg = options.get('company') # Get company argument

        if user_id:
            # --- Mode 1: User ID Provided ---
            # Company context is required but can be inferred or provided.
            self._handle_user_id_lookup(user_id, company_arg)
        else:
            # --- Mode 2: Name Provided ---
            # Company argument is strictly required here.
            if not company_arg:
                 raise CommandError("The --company argument is required when not specifying --user_id.")
            self._handle_name_company_lookup(company_arg) # Pass company_arg

        self.stdout.write(self.style.SUCCESS("Command finished."))

    # --- Handler for User ID Mode ---
    def _handle_user_id_lookup(self, user_id: str, company_arg: str | None):
        self.stdout.write(f"Processing lookup for User ID: {user_id}")
        try:
            # Use AUTH_USER_MODEL for flexibility if needed
            # User = get_user_model() # from django.contrib.auth import get_user_model
            user = User.objects.prefetch_related('company_associations__company').get(id=user_id)
        except User.DoesNotExist:
            raise CommandError(f"User with ID {user_id} not found.")
        except ValueError:
             raise CommandError(f"Invalid User ID format: {user_id}. Please provide a valid UUID.")

        if not user.first_name or not user.last_name:
            self.stdout.write(self.style.ERROR(f"User {user.id} ({user.email}) is missing First or Last Name. Cannot perform lookup."))
            return

        if user.linkedin_handle and not self.options['force']:
            self.stdout.write(self.style.WARNING(f"User {user.id} already has LinkedIn handle '{user.linkedin_handle}'. Use --force to overwrite."))
            return

        # --- Determine Company Context ---
        company_context_name = None
        if company_arg:
             # User explicitly provided a company, use that.
             self.stdout.write(f"Using provided company context: {company_arg}")
             company_context_name = company_arg
        else:
             # No company provided via arg, try to infer from user's associations
             self.stdout.write("Inferring company context from user associations...")
             associations = user.company_associations.all()
             association_count = associations.count()

             if association_count == 1:
                  company_context_name = associations[0].company.name
                  self.stdout.write(f"Found 1 associated company: {company_context_name}")
             elif association_count == 0:
                  raise CommandError(f"User {user.id} has no associated companies and no --company argument was provided. Cannot determine company context.")
             else:
                  # Multiple associations, ambiguous without --company argument
                  company_names = [assoc.company.name for assoc in associations]
                  raise CommandError(f"User {user.id} has multiple associated companies ({', '.join(company_names)}). Please specify which company to use with the --company argument.")

        # We must have a company_context_name at this point
        if not company_context_name:
             # This should not be reachable due to previous checks, but as a safeguard:
             raise CommandError("Failed to determine company context for the lookup.")

        # Proceed with lookup using user's name and determined company context
        first_name = user.first_name
        last_name = user.last_name

        self.stdout.write(f"Searching for: {first_name} {last_name} (Company Context: {company_context_name})")
        profile_info = self._find_profile(first_name, last_name, company_context_name)

        if not profile_info:
            self.stdout.write(self.style.ERROR(f"No LinkedIn profile found for User {user.id} ({first_name} {last_name}) with company context '{company_context_name}'"))
            return

        self._display_profile_info(profile_info)
        self._update_user_with_profile(user, profile_info, first_name, last_name)

    # --- Handler for Name + Company Mode ---
    def _handle_name_company_lookup(self, company_arg: str):
        # This mode *requires* --company, which we've already validated and received as company_arg
        first_name = self.options.get('first_name')
        last_name = self.options.get('last_name')

        # Validate required name arguments for this mode (company already validated)
        if not first_name or not last_name:
            raise CommandError("When --user_id is not provided, --first_name and --last_name are also required.")

        self.stdout.write(f"Looking up LinkedIn profile for: {first_name} {last_name} at {company_arg}")
        profile_info = self._find_profile(first_name, last_name, company_arg)

        if not profile_info:
            self.stdout.write(self.style.ERROR("No LinkedIn profile found based on the provided details."))
            return

        self._display_profile_info(profile_info)
        self.stdout.write(self.style.NOTICE("Results printed. No database records were updated in this mode."))


    # --- Helper methods (_find_profile, _display_profile_info, _update_user_with_profile, _might_be_name_change) ---
    # (These helper methods remain unchanged from the previous version)
    def _find_profile(self, first_name: str, last_name: str, company: str or None) -> dict or None:
        # ... (no change needed) ...
        try:
            profile_info = self.finder.find_profile(
                first_name=first_name,
                last_name=last_name,
                company=company or '', # Pass empty string if None
                search_engine=self.options['search_engine'],
                max_pages=self.options['max_pages']
            )
            return profile_info
        except Exception as e:
            logger.error(f"Error during LinkedIn lookup for {first_name} {last_name}: {e}", exc_info=True)
            self.stderr.write(self.style.ERROR(f"An error occurred during lookup: {e}"))
            return None

    def _display_profile_info(self, profile_info: dict):
        # ... (no change needed) ...
        self.stdout.write(self.style.SUCCESS(f"--- LinkedIn Profile Found ---"))
        self.stdout.write(f"  URL: {profile_info.get('url', 'N/A')}")
        self.stdout.write(f"  Handle: {profile_info.get('handle', 'N/A')}")
        self.stdout.write(f"  Confidence: {profile_info.get('confidence', 'N/A')}")
        if 'match_score' in profile_info:
            self.stdout.write(f"  Match Score: {profile_info['match_score']}")
        self.stdout.write(f"-----------------------------")

    def _update_user_with_profile(self, user: User, profile_info: dict, original_first_name: str, original_last_name: str):
        # ... (no change needed) ...
        try:
            old_handle = user.linkedin_handle
            new_handle = profile_info.get('handle')
            profile_url = profile_info.get('url')

            if not new_handle or not profile_url:
                 self.stdout.write(self.style.ERROR(f"Found profile data is incomplete (missing handle or url). Cannot update User {user.id}."))
                 return

            try:
                 relevance_score = float(profile_info.get('match_score', 0)) / 20.0 # Normalize 0-20 to 0-1
                 relevance_score = max(0.0, min(1.0, relevance_score))
            except (ValueError, TypeError):
                 relevance_score = 0.5

            user.linkedin_handle = new_handle

            if self._might_be_name_change(new_handle, original_first_name, original_last_name):
                if not isinstance(user.alternate_names, list):
                     user.alternate_names = []
                original_name = f"{original_first_name} {original_last_name}".strip()
                if original_name and original_name not in user.alternate_names:
                    user.alternate_names.append(original_name)
                    self.stdout.write(self.style.WARNING(
                        f"Handle '{new_handle}' suggests possible name change from '{original_name}'. Added to alternate names for User {user.id}."
                    ))

            linkedin_method_type, _ = ContactMethodType.objects.get_or_create(
                name="LinkedIn Profile", defaults={"category": "social"}
            )
            contact_method, created = UserContactMethod.objects.update_or_create(
                user=user, method_type=linkedin_method_type, defaults={"value": profile_url}
            )
            if self.verbose:
                action = "Created" if created else "Updated"
                self.stdout.write(f"{action} LinkedIn UserContactMethod for User {user.id}")

            source_link, created = UserSourceLink.objects.update_or_create(
                user=user, url=profile_url,
                defaults={
                    "source_type": "linkedin", "title": f"LinkedIn Profile: {new_handle}",
                    "relevance_score": relevance_score,
                    "notes": f"Found via lookup command on {timezone.now().strftime('%Y-%m-%d %H:%M')}"
                }
            )
            if self.verbose:
                action = "Created" if created else "Updated"
                self.stdout.write(f"{action} LinkedIn UserSourceLink for User {user.id}")

            user.save()
            self.stdout.write(self.style.SUCCESS(f"Successfully updated User {user.id} with LinkedIn handle: {new_handle}"))
            if old_handle and old_handle != new_handle:
                self.stdout.write(f"  Previous handle was: {old_handle}")

        except Exception as e:
            logger.error(f"Failed to update user {user.id} with LinkedIn data: {e}", exc_info=True)
            self.stderr.write(self.style.ERROR(f"Error updating user {user.id}: {e}"))


    def _might_be_name_change(self, handle: str, first_name: str, last_name: str) -> bool:
        # ... (no change needed) ...
        if not handle or not first_name or not last_name: return False
        handle_lower = handle.lower(); first_lower = first_name.lower(); last_lower = last_name.lower()
        handle_cleaned = ''.join(filter(str.isalpha, handle_lower))
        first_last = first_lower + last_lower; last_first = last_lower + first_lower
        if first_last in handle_cleaned or last_first in handle_cleaned: return False
        if first_lower not in handle_cleaned and last_lower not in handle_cleaned:
             if f"{first_lower[0]}{last_lower}" not in handle_lower and \
                f"{first_lower}{last_lower[0]}" not in handle_lower and \
                f"{first_lower[0]}-{last_lower}" not in handle_lower and \
                f"{first_lower}-{last_lower[0]}" not in handle_lower:
                 return True
        return False