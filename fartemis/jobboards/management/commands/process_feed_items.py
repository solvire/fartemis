"""
Claude wrote this. I'm not a fan of the structure.


For single item processing (useful for testing/debugging):
./manage.py process_feed_items --id 12345 --verbose

For batch processing all unprocessed items:
./manage.py process_feed_items --batch-size 100

For testing without making actual database changes:
./manage.py process_feed_items --dry-run


To process only LinkedIn items:
./manage.py process_feed_items --source linkedin


"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
import logging
import time

from fartemis.jobboards.models import FeedItem, FeedSource, Job
from fartemis.jobboards.mappers import LinkedInJobMapper
from fartemis.companies.mappers import CompanyMapper

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Process FeedItems into Job objects with company profiles'

    def add_arguments(self, parser):
        parser.add_argument(
            '--id', 
            type=int, 
            help='Process a specific FeedItem by ID'
        )
        parser.add_argument(
            '--batch-size', 
            type=int, 
            default=50,
            help='Number of FeedItems to process in one batch (default: 50)'
        )
        parser.add_argument(
            '--source', 
            type=str, 
            help='Process only FeedItems from a specific source (e.g., "linkedin")'
        )
        parser.add_argument(
            '--dry-run', 
            action='store_true', 
            help='Show what would be processed without actually creating Job objects'
        )
        parser.add_argument(
            '--limit', 
            type=int, 
            help='Limit the number of FeedItems to process'
        )
        parser.add_argument(
            '--verbose', 
            action='store_true', 
            help='Display detailed information during processing'
        )
        parser.add_argument(
            '--skip-company', 
            action='store_true', 
            help='Skip company profile creation/lookup'
        )
        parser.add_argument(
            '--user-id', 
            type=int, 
            help='Assign jobs to a specific user by ID'
        )
        parser.add_argument(
            '--username', 
            type=str, 
            help='Assign jobs to a specific user by username'
        )

    def handle(self, *args, **options):
        item_id = options.get('id')
        batch_size = options.get('batch_size')
        source_name = options.get('source')
        dry_run = options.get('dry_run')
        limit = options.get('limit')
        verbose = options.get('verbose')
        skip_company = options.get('skip_company')
        user_id = options.get('user_id')
        username = options.get('username')
        
        # Get user object if specified
        user = self._get_user(user_id, username, verbose)
        
        # Initialize company mapper
        self.company_mapper = None if skip_company else CompanyMapper()
        
        if item_id:
            # Process a specific item
            self.process_single_item(item_id, dry_run, verbose, skip_company, user)
        else:
            # Process unprocessed items chronologically
            self.process_unprocessed_items(batch_size, source_name, dry_run, limit, verbose, skip_company, user)
            
    def _get_user(self, user_id, username, verbose):
        """
        Get a user by ID or username.
        
        Returns:
            User object or None if not found or not specified
        """
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        if not user_id and not username:
            return None
            
        try:
            if user_id:
                user = User.objects.get(id=user_id)
                if verbose:
                    self.stdout.write(f"Found user by ID {user_id}: {user.username}")
                return user
                
            if username:
                user = User.objects.get(email=username)
                if verbose:
                    self.stdout.write(f"Found user by username {username}: {user.id}")
                return user
                
        except User.DoesNotExist:
            if user_id:
                self.stderr.write(self.style.ERROR(f"User with ID {user_id} not found"))
            else:
                self.stderr.write(self.style.ERROR(f"User with username '{username}' not found"))
            return None
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error retrieving user: {str(e)}"))
            return None

    def process_single_item(self, item_id, dry_run, verbose, skip_company, user=None):
        """
        Process a single FeedItem by ID.
        
        Args:
            item_id: ID of the FeedItem to process
            dry_run: If True, don't actually create/update objects
            verbose: If True, output detailed information
            skip_company: If True, skip company profile creation/lookup
            user: User object to associate with the job
        """
        try:
            item = FeedItem.objects.get(id=item_id)
            
            if item.is_processed and item.job:
                self.stdout.write(self.style.WARNING(
                    f'FeedItem {item_id} has already been processed (Job ID: {item.job.id})'
                ))
                return
            
            self.stdout.write(f'Processing FeedItem ID: {item_id} from source: {item.source.name}')
            
            if verbose:
                self.stdout.write(f'Item GUID: {item.guid}')
                if user:
                    self.stdout.write(f'Assigning to user: {user.email} (ID: {user.id})')
                
            if dry_run:
                self.stdout.write(self.style.SUCCESS(f'[DRY RUN] Would process FeedItem {item_id}'))
                return
                
            result = self._process_item(item, verbose, skip_company, user)
            
            if result:
                status = self.style.SUCCESS('SUCCESS')
                job_id = result.id if result else 'N/A'
            else:
                status = self.style.ERROR('FAILED')
                job_id = 'N/A'
                
            self.stdout.write(f'Processing result: {status} - Job ID: {job_id}')
            
        except FeedItem.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'FeedItem with ID {item_id} not found'))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error processing FeedItem {item_id}: {str(e)}'))
            if verbose:
                import traceback
                self.stderr.write(traceback.format_exc())

    def process_unprocessed_items(self, batch_size, source_name, dry_run, limit, verbose, skip_company, user=None):
        """
        Process unprocessed FeedItems chronologically starting with the oldest.
        
        Args:
            batch_size: Number of items to process in one transaction
            source_name: Name of feed source to filter by
            dry_run: If True, don't actually create/update objects
            limit: Maximum number of items to process
            verbose: If True, output detailed information
            skip_company: If True, skip company profile creation/lookup
            user: User object to associate with the job
        """
        # Build the query for unprocessed items
        query = FeedItem.objects.filter(is_processed=False)
        
        # Filter by source if specified
        if source_name:
            try:
                source = FeedSource.objects.get(name=source_name)
                query = query.filter(source=source)
            except FeedSource.DoesNotExist:
                self.stderr.write(self.style.ERROR(f'FeedSource with name "{source_name}" not found'))
                return
        
        # Order by creation date (oldest first)
        query = query.order_by('created_at')
        
        # Limit if specified
        if limit:
            query = query[:limit]
            
        total_items = query.count()
        
        if total_items == 0:
            self.stdout.write(self.style.SUCCESS('No unprocessed FeedItems found'))
            return
            
        self.stdout.write(f'Found {total_items} unprocessed FeedItems')
        if user:
            self.stdout.write(f'All jobs will be assigned to user: {user.username} (ID: {user.id})')
        
        if dry_run:
            self.stdout.write(self.style.SUCCESS(f'[DRY RUN] Would process {total_items} FeedItems'))
            return
            
        # Process in batches
        processed = 0
        successful = 0
        failed = 0
        
        # Calculate estimated time for progress display
        start_time = time.time()
        
        for i, item in enumerate(query):
            if verbose:
                self.stdout.write(f'Processing item {i+1} of {total_items} - ID: {item.id}, GUID: {item.guid}')
            else:
                # Simple progress indicator
                if (i+1) % 10 == 0 or (i+1) == total_items:
                    elapsed = time.time() - start_time
                    if i > 0:
                        # Calculate estimated remaining time
                        items_per_sec = (i+1) / elapsed
                        remaining_items = total_items - (i+1)
                        remaining_secs = remaining_items / items_per_sec if items_per_sec > 0 else 0
                        
                        self.stdout.write(f'Processed {i+1}/{total_items} items '
                                         f'({successful} successful, {failed} failed) - '
                                         f'Est. remaining time: {int(remaining_secs//60)}m {int(remaining_secs%60)}s')
            
            try:
                result = self._process_item(item, verbose, skip_company, user)
                processed += 1
                
                if result:
                    successful += 1
                else:
                    failed += 1
                    
                # Commit after each batch to avoid large transactions
                if processed % batch_size == 0:
                    self.stdout.write(f'Committing batch of {batch_size} items')
                    
            except Exception as e:
                failed += 1
                self.stderr.write(self.style.ERROR(f'Error processing FeedItem {item.id}: {str(e)}'))
                if verbose:
                    import traceback
                    self.stderr.write(traceback.format_exc())
                
        # Show final stats
        self.stdout.write(self.style.SUCCESS(
            f'Processing complete. Processed {processed} items: '
            f'{successful} successful, {failed} failed'
        ))

    def _process_item(self, item, verbose, skip_company, user):
        """
        Process a single FeedItem and return the created Job (if successful).
        """
        with transaction.atomic():
            try:
                # Determine the appropriate mapper based on source
                if item.source.name == 'linkedin':
                    mapper = LinkedInJobMapper()
                else:
                    self.stderr.write(self.style.WARNING(
                        f'No mapper available for source: {item.source.name}'
                    ))
                    return None
                
                # Extract data components from raw_data
                raw_data = item.raw_data
                
                if verbose:
                    self.stdout.write(f'Raw data keys: {", ".join(raw_data.keys())}')
                
                job_summary = raw_data.get('job_summary', {})
                job_details = raw_data.get('job_details', {})
                
                # Map to Job object
                job = mapper.map_job(job_summary, job_details, user)
                
                if job:
                    # Process company information if not skipped
                    if not skip_company and self.company_mapper:
                        try:
                            if verbose:
                                self.stdout.write(f'Processing company information for: {job.company_name}')
                            
                            company_profile = self.company_mapper.get_or_create_company(raw_data)
                            
                            if company_profile:
                                # Link the company profile to the job
                                job.company_profile = company_profile
                                job.save()
                                
                                if verbose:
                                    self.stdout.write(self.style.SUCCESS(
                                        f'Linked company profile: {company_profile.name} (ID: {company_profile.id})'
                                    ))
                            else:
                                if verbose:
                                    self.stdout.write(self.style.WARNING(
                                        f'Could not create company profile for: {job.company_name}'
                                    ))
                        except Exception as e:
                            self.stderr.write(self.style.ERROR(f'Error processing company information: {str(e)}'))
                    
                    # Link the job back to the feed item
                    item.job = job
                    item.is_processed = True
                    item.save()
                    
                    if verbose:
                        self.stdout.write(f'Created Job: {job.title} (ID: {job.id})')
                    
                    return job
                else:
                    if verbose:
                        self.stdout.write(self.style.WARNING(f'Mapper returned None for item {item.id}'))
                    return None
                    
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'Error in _process_item for {item.id}: {str(e)}'))
                if verbose:
                    import traceback
                    self.stderr.write(traceback.format_exc())
                raise