"""
# Search for companies by name
./manage.py linkedin_companies --search "Adobe" --limit 5

# Fetch a specific company by ID
./manage.py linkedin_companies --company-id 1234567 --verbose

# Save results to a JSON file
./manage.py linkedin_companies --search "Tech Startups" --output json --output-file companies.json
"""
from django.core.management.base import BaseCommand, CommandError
from typing import List, Optional, Dict, Any
import logging
import json
import time
from datetime import datetime

from linkedin_api import Linkedin
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Search for companies or fetch company details from LinkedIn'

    def add_arguments(self, parser):
        # Create mutually exclusive group
        group = parser.add_mutually_exclusive_group(required=True)
        
        # Search companies arguments
        group.add_argument(
            '--search',
            dest='search_keywords',
            help='Search for companies by keywords (comma-separated)'
        )
        
        # Get company arguments
        group.add_argument(
            '--company-id',
            dest='company_id',
            help='Fetch a specific company by LinkedIn ID'
        )
        
        # Other options
        parser.add_argument(
            '--limit',
            type=int,
            default=10,
            help='Limit the number of search results (default: 10)'
        )
        
        parser.add_argument(
            '--output',
            choices=['console', 'json'],
            default='console',
            help='Output format (default: console)'
        )
        
        parser.add_argument(
            '--output-file',
            help='File to save output to (only used when output=json)'
        )
        
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose output'
        )

    def handle(self, *args, **options):
        # Extract options
        search_keywords = options.get('search_keywords')
        company_id = options.get('company_id')
        limit = options.get('limit')
        output_format = options.get('output')
        output_file = options.get('output_file')
        verbose = options.get('verbose')
        
        # Initialize LinkedIn API client
        api = self._initialize_linkedin_api(verbose)
        if not api:
            raise CommandError("Failed to initialize LinkedIn API client")
        
        results = None
        
        # Process based on command mode
        if search_keywords:
            # Search mode
            keywords = [k.strip() for k in search_keywords.split(',') if k.strip()]
            self.stdout.write(f"Searching for companies with keywords: {', '.join(keywords)}")
            results = self.search_companies(api, keywords, limit=limit, verbose=verbose)
            
            if results:
                self.stdout.write(self.style.SUCCESS(f"Found {len(results)} companies"))
            else:
                self.stdout.write(self.style.WARNING("No companies found matching the keywords"))
                
        elif company_id:
            # Get company mode
            self.stdout.write(f"Fetching company with ID: {company_id}")
            company = self.get_company(api, company_id, verbose=verbose)
            
            if company:
                self.stdout.write(self.style.SUCCESS(f"Successfully retrieved company: {company.get('name', company_id)}"))
                results = [company]  # Put in list for consistent output handling
            else:
                self.stdout.write(self.style.ERROR(f"Company with ID {company_id} not found"))
                return
        
        # Handle output
        if not results:
            return
            
        if output_format == 'console':
            self._display_results(results)
        else:  # json
            output_path = output_file or f"linkedin_companies_{timezone.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(output_path, 'w') as f:
                json.dump(results, f, indent=2)
            self.stdout.write(self.style.SUCCESS(f"Results saved to {output_path}"))

    def _initialize_linkedin_api(self, verbose=False):
        """
        Initialize the LinkedIn API client.
        
        Returns:
            Linkedin client instance or None if initialization fails
        """
        try:
            # Check for required settings
            if not hasattr(settings, 'LINKEDIN_USERNAME') or not hasattr(settings, 'LINKEDIN_PASSWORD'):
                self.stderr.write(self.style.ERROR(
                    "LinkedIn credentials not found in settings. "
                    "Please add LINKEDIN_USERNAME and LINKEDIN_PASSWORD to your settings."
                ))
                return None
                
            # Create LinkedIn client
            api = Linkedin(
                settings.LINKEDIN_USERNAME,
                settings.LINKEDIN_PASSWORD
            )
            
            if verbose:
                self.stdout.write("LinkedIn API client initialized successfully")
                
            return api
            
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error initializing LinkedIn API client: {str(e)}"))
            return None

    def search_companies(self, api, keywords: Optional[List[str]] = None, limit: int = 10, verbose: bool = False) -> List:
        """
        Search for companies using keywords.
        
        Args:
            api: LinkedIn API client
            keywords: List of keywords to search for
            limit: Maximum number of results to return
            verbose: Whether to display verbose information
            
        Returns:
            List of company data dictionaries
        """
        if not keywords:
            self.stderr.write(self.style.WARNING("No keywords provided for company search"))
            return []
            
        try:
            # Join multiple keywords for search
            keyword_str = ' '.join(keywords)
            
            if verbose:
                self.stdout.write(f"Searching for companies with keyword string: '{keyword_str}'")
                
            # Call LinkedIn API to search for companies
            companies = api.search_companies(keyword_str, limit=limit)
            
            if verbose:
                self.stdout.write(f"Search returned {len(companies)} companies")
                
            # Enhance company data with full profiles
            enhanced_companies = []
            
            for i, company in enumerate(companies):
                if verbose:
                    self.stdout.write(f"Fetching details for company {i+1}/{len(companies)}: {company.get('name', 'Unknown')}")
                
                try:
                    # Extract company ID
                    company_id = company.get('urn_id', '').split(':')[-1]
                    
                    if not company_id:
                        self.stderr.write(self.style.WARNING(f"Could not extract ID for company: {company.get('name', 'Unknown')}"))
                        continue
                        
                    # Fetch full company profile
                    company_data = self.get_company(api, company_id, verbose=verbose)
                    
                    if company_data:
                        enhanced_companies.append(company_data)
                        
                        # Add a delay to avoid rate limiting
                        if i < len(companies) - 1:
                            time.sleep(1)
                    
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"Error fetching details for company {company.get('name', 'Unknown')}: {str(e)}"))
                    continue
            
            return enhanced_companies
            
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error searching for companies: {str(e)}"))
            return []

    def get_company(self, api, public_id, verbose=False):
        """
        Get company details by LinkedIn public ID.
        
        Args:
            api: LinkedIn API client
            public_id: LinkedIn company ID
            verbose: Whether to display verbose information
            
        Returns:
            Company data dictionary or None if not found
        """
        try:
            if verbose:
                self.stdout.write(f"Fetching company details for ID: {public_id}")
                
            # Call LinkedIn API to get company details
            company_data = api.get_company(public_id)
            
            if not company_data:
                self.stderr.write(self.style.WARNING(f"No data returned for company ID: {public_id}"))
                return None
                
            # Extract additional data that might be useful
            try:
                # Get company updates
                if verbose:
                    self.stdout.write(f"Fetching company updates for ID: {public_id}")
                    
                updates = api.get_company_updates(public_id, limit=5)
                if updates:
                    company_data['recent_updates'] = updates
                    
                # Get company employees
                if verbose:
                    self.stdout.write(f"Fetching employee count for ID: {public_id}")
                    
                employees = api.search_people(keywords=None, companies=[public_id], limit=1)
                if employees and 'total' in employees:
                    company_data['employee_count_estimate'] = employees['total']
                    
            except Exception as e:
                if verbose:
                    self.stderr.write(self.style.WARNING(f"Error fetching additional company data: {str(e)}"))
            
            return company_data
            
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error fetching company details for ID {public_id}: {str(e)}"))
            return None

    def _display_results(self, results):
        """
        Display search results in a human-readable format.
        """
        self.stdout.write("\n===== Company Results =====\n")
        
        for i, company in enumerate(results):
            self.stdout.write(f"Company {i+1}:")
            self.stdout.write(f"  Name: {company.get('name', 'Unknown')}")
            self.stdout.write(f"  ID: {company.get('id', company.get('entityUrn', 'Unknown'))}")
            self.stdout.write(f"  Industry: {company.get('industryName', 'Unknown')}")
            self.stdout.write(f"  Website: {company.get('website', 'Unknown')}")
            self.stdout.write(f"  HQ: {company.get('headquarter', {}).get('city', 'Unknown')}, {company.get('headquarter', {}).get('country', '')}")
            self.stdout.write(f"  Size: {company.get('staffCount', company.get('employeeCountRange', {}).get('start', 'Unknown'))}")
            
            # Show recent funding if available
            if 'fundingData' in company and company['fundingData']:
                funding = company['fundingData']
                self.stdout.write(f"  Latest Funding: {funding.get('lastFundingAmount', 'Unknown')} ({funding.get('lastFundingType', 'Unknown')})")
                self.stdout.write(f"  Total Funding: {funding.get('totalFundingAmount', 'Unknown')}")
            
            # Add founded date if available
            if 'foundedOn' in company and company['foundedOn']:
                founded = company['foundedOn']
                if isinstance(founded, dict) and 'year' in founded:
                    self.stdout.write(f"  Founded: {founded['year']}")
                elif isinstance(founded, str):
                    self.stdout.write(f"  Founded: {founded}")
            
            # Add separator between companies
            if i < len(results) - 1:
                self.stdout.write("\n" + "-" * 40 + "\n")