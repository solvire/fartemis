from django.core.management.base import BaseCommand
from fartemis.companies.controllers import CompanyResearchController
from fartemis.companies.models import CompanyProfile
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Research company profiles and update them with AI-generated data'

    def add_arguments(self, parser):
        parser.add_argument('--company-id', type=int, help='ID of specific company to research')
        parser.add_argument('--batch-size', type=int, default=1, 
                            help='Number of companies to process (default: 1)')
        parser.add_argument('--force', action='store_true', 
                            help='Force update even for recently updated companies')

    def handle(self, *args, **options):
        company_id = options.get('company_id')
        batch_size = options.get('batch_size')
        force = options.get('force')
        
        # Initialize controller
        controller = CompanyResearchController()
        
        if company_id:
            # Process specific company
            try:
                company = CompanyProfile.objects.get(id=company_id)
                self.stdout.write(f"Researching company: {company.name}")
                
                updated_company = controller.research_company(company_id)
                
                self.stdout.write(self.style.SUCCESS(
                    f"Successfully updated company profile for {updated_company.name}"
                ))
                
            except CompanyProfile.DoesNotExist:
                self.stderr.write(self.style.ERROR(f"Company with ID {company_id} not found"))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Error researching company: {str(e)}"))
        else:
            # Process batch of companies
            query = CompanyProfile.objects.all()
            
            if not force:
                # Prioritize companies with no sentiment data first
                query = query.filter(last_sentiment_update__isnull=True)
                
                # If no companies without sentiment data, get oldest updated
                if not query.exists():
                    query = CompanyProfile.objects.all().order_by('last_sentiment_update')
            
            companies = query[:batch_size]
            
            if not companies:
                self.stdout.write("No companies found to process")
                return
            
            for company in companies:
                try:
                    self.stdout.write(f"Researching company: {company.name}")
                    
                    updated_company = controller.research_company(company.id)
                    
                    self.stdout.write(self.style.SUCCESS(
                        f"Successfully updated company profile for {updated_company.name}"
                    ))
                    
                except Exception as e:
                    self.stderr.write(self.style.ERROR(
                        f"Error researching company {company.name}: {str(e)}"
                    ))