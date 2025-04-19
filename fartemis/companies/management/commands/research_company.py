from django.core.management.base import BaseCommand
from fartemis.companies.controllers import CompanyResearchController
from fartemis.companies.models import CompanyProfile
import logging

# Import LLM classes
from langchain.chat_models import init_chat_model
from langchain_deepseek import ChatDeepSeek

from fartemis.llms.clients import LLMClientFactory
from fartemis.llms.constants import LLMProvider

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Research company profiles and update them with AI-generated data'

    def add_arguments(self, parser):
        parser.add_argument('--company-id', type=int, help='ID of specific company to research')
        parser.add_argument('--batch-size', type=int, default=1, 
                            help='Number of companies to process (default: 1)')
        parser.add_argument('--force', action='store_true', 
                            help='Force update even for recently updated companies')
        parser.add_argument(
            '--provider',
            type=str,
            choices=[p[0] for p in LLMProvider.CHOICES],
            help=f'LLM provider to test (default: from settings)'
        )
        
        # Model selection
        parser.add_argument(
            '--model',
            type=str,
            help='Model to use (provider-specific, uses default if not specified)'
        )

        # LLM parameters
        parser.add_argument(
            '--temperature',
            type=float,
            help='Temperature parameter for generation (override settings)'
        )
        parser.add_argument(
            '--max-tokens',
            type=int,
            help='Maximum tokens to generate (override settings)'
        )

    def handle(self, *args, **options):
        company_id = options.get('company_id')
        batch_size = options.get('batch_size')
        force = options.get('force')
        provider = options.get('provider')
        model = options.get('model')

        default_params = {}
        if options['temperature'] is not None:
            default_params['temperature'] = options['temperature']
        if options['max_tokens'] is not None:
            default_params['max_tokens'] = options['max_tokens']


        client = LLMClientFactory.create(
            provider=provider,
            model=model,
            default_params=default_params if default_params else None
        )

        self.stdout.write(self.style.SUCCESS(
            f"Initialized {LLMProvider.get_display_name(provider)} client with model: {client.model}"
        ))
    

        llm = init_chat_model(model=client.get_model(), model_provider=provider)
        
        # Initialize controller with the selected LLM
        controller = CompanyResearchController(llm=llm)
        
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