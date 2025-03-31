from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q
import logging
from fartemis.companies.models import CompanyProfile
from fartemis.companies.controllers import CompanyResearchController

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Find and update career pages for company profiles'

    def add_arguments(self, parser):
        parser.add_argument('--company-id', type=int, 
                            help='ID of specific company to update career page for')
        parser.add_argument('--batch-size', type=int, default=10, 
                            help='Number of companies to process (default: 10)')
        parser.add_argument('--force', action='store_true', 
                            help='Force update even for companies with existing career pages')
        parser.add_argument('--days-since-update', type=int, default=30,
                            help='Only update companies not updated in this many days (default: 30)')

    def handle(self, *args, **options):
        company_id = options.get('company_id')
        batch_size = options.get('batch_size')
        force = options.get('force')
        days_since_update = options.get('days_since_update')
        
        # Initialize controller
        controller = CompanyResearchController()
        
        # Set up processing counter
        processed_count = 0
        updated_count = 0
        
        # Process specific company if ID provided
        if company_id:
            try:
                company = CompanyProfile.objects.get(id=company_id)
                self.stdout.write(f"Checking careers page for: {company.name}")
                
                if company.careers_page_url and not force:
                    self.stdout.write(f"Company already has careers page: {company.careers_page_url}")
                else:
                    result = self._update_careers_page(company, controller)
                    if result:
                        updated_count += 1
                        self.stdout.write(self.style.SUCCESS(
                            f"Updated careers page for {company.name}: {company.careers_page_url}"
                        ))
                    else:
                        self.stdout.write(self.style.WARNING(
                            f"Could not find careers page for {company.name}"
                        ))
            except CompanyProfile.DoesNotExist:
                self.stderr.write(self.style.ERROR(f"Company with ID {company_id} not found"))
        else:
            # Build query for companies without careers pages or not recently updated
            cutoff_date = timezone.now() - timezone.timedelta(days=days_since_update)
            
            query = CompanyProfile.objects.all()
            
            if not force:
                query = query.filter(
                    Q(careers_page_url__isnull=True) | 
                    Q(careers_page_url='') |
                    Q(last_sentiment_update__lt=cutoff_date)
                )
                
            # Order by missing careers page first, then by oldest update
            query = query.order_by(
                'careers_page_url', 
                'last_sentiment_update'
            )
            
            companies = query[:batch_size]
            total_count = companies.count()
            
            if total_count == 0:
                self.stdout.write("No companies found that need career page updates")
                return
                
            self.stdout.write(f"Found {total_count} companies to process")
            
            # Process each company
            for company in companies:
                processed_count += 1
                self.stdout.write(f"[{processed_count}/{total_count}] Checking careers page for: {company.name}")
                
                if company.careers_page_url and not force:
                    self.stdout.write(f"  Company already has careers page: {company.careers_page_url}")
                    continue
                    
                result = self._update_careers_page(company, controller)
                if result:
                    updated_count += 1
                    self.stdout.write(self.style.SUCCESS(
                        f"  Updated careers page for {company.name}: {company.careers_page_url}"
                    ))
                else:
                    self.stdout.write(self.style.WARNING(
                        f"  Could not find careers page for {company.name}"
                    ))
        
        # Print summary
        self.stdout.write(f"\nProcessed {processed_count} companies, updated {updated_count} career pages")
    
    def _update_careers_page(self, company, controller):
        """
        Use the controller to find and update a company's careers page
        
        Returns:
            bool: True if careers page was found and updated, False otherwise
        """
        try:
            # Generate a focused query specifically for finding the careers page
            query = f"{company.name} careers page jobs"
            
            # Use the existing controller method to find the careers page
            # This assumes you have the _find_careers_page method in your controller
            careers_url = controller._find_careers_page(company, [])
            
            if careers_url:
                # Update the company profile with the found careers page URL
                company.careers_page_url = careers_url
                company.save(update_fields=['careers_page_url'])
                logger.info(f"Updated careers page for {company.name}: {careers_url}")
                return True
            else:
                logger.warning(f"Could not find careers page for {company.name}")
                return False
                
        except Exception as e:
            logger.error(f"Error finding careers page for {company.name}: {str(e)}")
            return False