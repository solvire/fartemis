import re
import logging
import traceback
from typing import Dict, Any, Optional, Tuple, List
from difflib import SequenceMatcher
from django.db.models import Q

from fartemis.companies.models import CompanyProfile
from linkedin_api import Linkedin
from django.conf import settings

logger = logging.getLogger(__name__)

class CompanyMapper:
    """
    Maps LinkedIn company data to CompanyProfile objects.
    Handles finding existing companies or creating new ones.
    """
    
    def __init__(self):
        self.linkedin_api = None
    
    def initialize_linkedin_api(self):
        """Initialize LinkedIn API client if not already initialized."""
        if self.linkedin_api is not None:
            return True
            
        try:
            # Check for required settings
            if not hasattr(settings, 'LINKEDIN_USERNAME') or not hasattr(settings, 'LINKEDIN_PASSWORD'):
                logger.error("LinkedIn credentials not found in settings")
                return False
                
            # Create LinkedIn client
            self.linkedin_api = Linkedin(
                settings.LINKEDIN_USERNAME,
                settings.LINKEDIN_PASSWORD
            )
            return True
            
        except Exception as e:
            logger.error(f"Error initializing LinkedIn API client: {str(e)}")
            return False
    
    def get_or_create_company(self, job_data: Dict[str, Any]) -> Optional[CompanyProfile]:
        """
        Extract company info from job data and either find an existing company
        or create a new one.
        
        Args:
            job_data: Dictionary containing job details, including company information
            
        Returns:
            CompanyProfile instance or None if extraction failed
        """
        try:
            # Extract basic company info from job data
            company_info = self._extract_company_info_from_job(job_data)
            
            if not company_info or not company_info.get('name'):
                logger.warning("Could not extract company name from job data")
                return None
            
            # Try to find existing company
            existing_company = self._find_existing_company(company_info)
            
            if existing_company:
                logger.info(f"Found existing company: {existing_company.name} (ID: {existing_company.id})")
                return existing_company
            
            # If LinkedIn ID is available, try to get full company data
            linkedin_id = company_info.get('linkedin_id')
            if linkedin_id and self.initialize_linkedin_api():
                try:
                    company_data = self.linkedin_api.get_company(linkedin_id)
                    if company_data:
                        return self._create_company_from_linkedin_data(company_data)
                except Exception as e:
                    logger.error(f"Error fetching LinkedIn company data: {str(e)}")
            
            # Fallback to creating company with minimal info
            return self._create_company_from_job_data(company_info)
            
        except Exception as e:
            logger.error(f"Error in get_or_create_company: {str(e)}")
            return None
    
    def _extract_company_info_from_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract basic company information from job data.
        
        Args:
            job_data: Dictionary containing job details
            
        Returns:
            Dictionary with extracted company information
        """
        import logging
        logger = logging.getLogger(__name__)
        
        company_info = {
            'name': None,
            'linkedin_id': None,
            'website': None,
            'headquarters_city': None,
            'headquarters_country': None
        }
        
        # Debug logging to see the structure
        if 'job_details' in job_data:
            if 'companyDetails' in job_data['job_details']:
                logger.debug(f"Found companyDetails in job_details: {type(job_data['job_details']['companyDetails'])}")
        
        # Extract from job_details if available
        job_details = job_data.get('job_details', {})
        
        if job_details and 'companyDetails' in job_details:
            company_details = job_details['companyDetails']
            
            # Check if the LinkedIn structure uses the WebCompactJobPostingCompany recipe
            if 'com.linkedin.voyager.deco.jobs.web.shared.WebCompactJobPostingCompany' in company_details:
                web_compact = company_details['com.linkedin.voyager.deco.jobs.web.shared.WebCompactJobPostingCompany']
                
                # Extract LinkedIn ID from company URN
                if 'company' in web_compact:
                    company_urn = web_compact.get('company', '')
                    if company_urn:
                        company_info['linkedin_id'] = company_urn.split(':')[-1]
                
                # Extract company info from companyResolutionResult
                if 'companyResolutionResult' in web_compact:
                    resolution = web_compact['companyResolutionResult']
                    
                    # Extract name
                    company_info['name'] = resolution.get('name')
                    
                    # Extract website
                    company_info['website'] = resolution.get('url')
                    
                    # Extract LinkedIn ID from entityUrn if not already extracted
                    if not company_info['linkedin_id'] and 'entityUrn' in resolution:
                        entity_urn = resolution.get('entityUrn', '')
                        if entity_urn:
                            company_info['linkedin_id'] = entity_urn.split(':')[-1]
            
            # Traditional structure checks (fallback)
            else:
                # Extract name
                company_info['name'] = company_details.get('name')
                
                # Extract LinkedIn ID
                if 'company' in company_details:
                    company_urn = company_details['company'].get('entityUrn', '')
                    if company_urn:
                        company_info['linkedin_id'] = company_urn.split(':')[-1]
                
                # Extract website
                company_info['website'] = company_details.get('companyUrl')
                
                # Extract headquarters location
                if 'headquarter' in company_details:
                    company_info['headquarters_city'] = company_details['headquarter'].get('city')
                    company_info['headquarters_country'] = company_details['headquarter'].get('country')
        
        # If not found in job_details, try job_summary
        if not company_info['name'] and 'job_summary' in job_data:
            job_summary = job_data.get('job_summary', {})
            
            # Try to extract from company field if available
            if 'company' in job_summary:
                company_urn = job_summary['company'].get('entityUrn', '')
                if company_urn:
                    company_info['linkedin_id'] = company_urn.split(':')[-1]
                company_info['name'] = job_summary['company'].get('name')
                
            # Or from companyName field
            elif 'companyName' in job_summary:
                company_info['name'] = job_summary.get('companyName')
        
        # Additional extraction for company name from nested structures
        # This covers the case where company name is nested deeply
        if not company_info['name']:
            # Look for company name in any nested dictionaries under companyDetails
            def find_company_name(obj):
                if isinstance(obj, dict):
                    if 'name' in obj and isinstance(obj['name'], str) and 'company' in obj.get('entityUrn', ''):
                        return obj['name']
                    for key, value in obj.items():
                        result = find_company_name(value)
                        if result:
                            return result
                elif isinstance(obj, list):
                    for item in obj:
                        result = find_company_name(item)
                        if result:
                            return result
                return None
            
            if 'job_details' in job_data and 'companyDetails' in job_data['job_details']:
                company_name = find_company_name(job_data['job_details']['companyDetails'])
                if company_name:
                    company_info['name'] = company_name
        
        # Try to get companyName directly from job_details as a last resort
        if not company_info['name'] and job_details and 'companyName' in job_details:
            company_info['name'] = job_details.get('companyName')
        
        # Debug logging for troubleshooting
        logger.debug(f"Extracted company info: {company_info}")
        
        return company_info
    
    def _find_existing_company(self, company_info: Dict[str, Any]) -> Optional[CompanyProfile]:
        """
        Try to find an existing company profile matching the given info.
        First tries to match by LinkedIn ID, then by name.
        
        Args:
            company_info: Dictionary with company information
            
        Returns:
            CompanyProfile instance or None if not found
        """
        # Try to find by LinkedIn ID if available
        linkedin_id = company_info.get('linkedin_id')
        if linkedin_id:
            # Placeholder for future LinkedIn ID field
            # For now, we might store it in notes or use name matching
            pass
        
        # Try to find by exact name match
        company_name = company_info.get('name')
        if company_name:
            # Try exact match first
            exact_match = CompanyProfile.objects.filter(name__iexact=company_name).first()
            if exact_match:
                return exact_match
            
            # If no exact match, try normalized name matching
            normalized_name = self._normalize_company_name(company_name)
            for company in CompanyProfile.objects.all():
                if self._normalize_company_name(company.name) == normalized_name:
                    return company
            
            # If still no match, try fuzzy matching
            best_match, score = self._find_best_fuzzy_match(company_name)
            if best_match and score > 0.85:  # 85% similarity threshold
                return best_match
        
        return None
    
    def _create_company_from_linkedin_data(self, company_data: Dict[str, Any]) -> CompanyProfile:
        """
        Create a CompanyProfile from LinkedIn API data.
        
        Args:
            company_data: Dictionary with LinkedIn company data
            
        Returns:
            Created CompanyProfile instance
        """
        import traceback
        
        try:
            # Extract data from LinkedIn response
            name = company_data.get('name', 'Unknown Company')
            
            # Extract website - can be in different fields
            website = company_data.get('website') or company_data.get('companyPageUrl')
            
            # Extract description - can be a string directly or nested in a dictionary
            description = None
            if 'description' in company_data:
                if isinstance(company_data['description'], str):
                    description = company_data['description']
                elif isinstance(company_data['description'], dict) and 'text' in company_data['description']:
                    description = company_data['description'].get('text', '')
            
            # Extract founded year
            founded_year = None
            if 'foundedOn' in company_data and company_data['foundedOn']:
                founded = company_data['foundedOn']
                if isinstance(founded, dict) and 'year' in founded:
                    founded_year = founded['year']
                # Handle integer directly
                elif isinstance(founded, int):
                    founded_year = founded
            
            # Extract employee count
            employee_count_min = None
            employee_count_max = None
            
            # Try staffCountRange
            if 'staffCountRange' in company_data:
                if isinstance(company_data['staffCountRange'], dict):
                    employee_count_min = company_data['staffCountRange'].get('start')
                    employee_count_max = company_data['staffCountRange'].get('end')
            
            # Or try employeeCountRange
            elif 'employeeCountRange' in company_data:
                if isinstance(company_data['employeeCountRange'], dict):
                    employee_count_min = company_data['employeeCountRange'].get('start')
                    employee_count_max = company_data['employeeCountRange'].get('end')
            
            # Also check for direct staffCount
            elif 'staffCount' in company_data:
                employee_count_min = company_data.get('staffCount')
            
            # Extract headquarters location
            headquarters_city = None
            headquarters_country = None
            
            if 'headquarter' in company_data:
                if isinstance(company_data['headquarter'], dict):
                    headquarters_city = company_data['headquarter'].get('city')
                    headquarters_country = company_data['headquarter'].get('country')
            
            # Also check in confirmedLocations for headquarters
            elif 'confirmedLocations' in company_data and isinstance(company_data['confirmedLocations'], list):
                for location in company_data['confirmedLocations']:
                    if location.get('headquarter') is True:
                        headquarters_city = location.get('city')
                        headquarters_country = location.get('country')
                        break
            
            # Check if public company
            is_public = False
            stock_symbol = None
            
            if 'companyType' in company_data:
                if isinstance(company_data['companyType'], str) and company_data['companyType'] == 'PUBLIC_COMPANY':
                    is_public = True
                elif isinstance(company_data['companyType'], dict) and company_data['companyType'].get('code') == 'PUBLIC_COMPANY':
                    is_public = True
                # Also check if the entry is another structure
                elif isinstance(company_data['companyType'], dict) and company_data['companyType'].get('localizedName') == 'Public Company':
                    is_public = True
            
            # Extract LinkedIn ID
            linkedin_id = None
            if 'id' in company_data:
                linkedin_id = company_data['id']
            elif 'entityUrn' in company_data:
                linkedin_id = company_data['entityUrn'].split(':')[-1]
            
            # Create company profile
            company = CompanyProfile.objects.create(
                name=name,
                website=website,
                description=description,
                founded_year=founded_year,
                employee_count_min=employee_count_min,
                employee_count_max=employee_count_max,
                headquarters_city=headquarters_city,
                headquarters_country=headquarters_country,
                is_public=is_public,
                stock_symbol=stock_symbol,
                # Store LinkedIn ID in notes for now until we add a dedicated field
                notes=f"LinkedIn ID: {linkedin_id}" if linkedin_id else None,
                linkedin_id=linkedin_id
            )
            
            return company
            
        except Exception as e:
            # Print the stack trace for debugging
            traceback.print_exc()
            logger.error(f"Error creating company from LinkedIn data: {str(e)}")
            
            # Fallback to minimal company creation
            try:
                return CompanyProfile.objects.create(
                    name=company_data.get('name', 'Unknown Company')
                )
            except Exception as e2:
                logger.error(f"Error creating minimal company profile: {str(e2)}")
                return CompanyProfile.objects.create(
                    name='Unknown Company'
                )
    
    def _create_company_from_job_data(self, company_info: Dict[str, Any]) -> CompanyProfile:
        """
        Create a CompanyProfile with minimal information from job data.
        
        Args:
            company_info: Dictionary with basic company information
            
        Returns:
            Created CompanyProfile instance
        """
        try:
            return CompanyProfile.objects.create(
                name=company_info.get('name', 'Unknown Company'),
                website=company_info.get('website'),
                headquarters_city=company_info.get('headquarters_city'),
                headquarters_country=company_info.get('headquarters_country'),
                notes=f"LinkedIn ID: {company_info.get('linkedin_id', '')}" if company_info.get('linkedin_id') else None
            )
        except Exception as e:
            logger.error(f"Error creating company from job data: {str(e)}")
            return CompanyProfile.objects.create(
                name=company_info.get('name', 'Unknown Company')
            )
    
    def _normalize_company_name(self, name: str) -> str:
        """
        Normalize company name for better matching.
        Removes common suffixes, extra spaces, and converts to lowercase.
        
        Args:
            name: Original company name
            
        Returns:
            Normalized company name
        """
        if not name:
            return ""
            
        # Convert to lowercase
        normalized = name.lower()
        
        # Remove common legal suffixes
        suffixes = [
            r'\binc\.?$', r'\bcorp\.?$', r'\bcorporation$', r'\bltd\.?$',
            r'\bllc$', r'\bllp$', r'\bp\.?c\.?$', r'\bindustries$',
            r'\bcompany$', r'\bco\.?$', r'\bgroup$', r'\bholdings$'
        ]
        
        for suffix in suffixes:
            normalized = re.sub(suffix, '', normalized)
        
        # Remove special characters and extra whitespace
        normalized = re.sub(r'[^\w\s]', ' ', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized
    
    def _find_best_fuzzy_match(self, company_name: str) -> Tuple[Optional[CompanyProfile], float]:
        """
        Find the best fuzzy match for a company name.
        
        Args:
            company_name: Company name to match
            
        Returns:
            Tuple of (CompanyProfile, match_score) or (None, 0.0) if no good match
        """
        if not company_name:
            return None, 0.0
            
        best_match = None
        best_score = 0.0
        
        normalized_name = self._normalize_company_name(company_name)
        
        for company in CompanyProfile.objects.all():
            normalized_company_name = self._normalize_company_name(company.name)
            
            # Calculate similarity ratio
            similarity = SequenceMatcher(None, normalized_name, normalized_company_name).ratio()
            
            if similarity > best_score:
                best_score = similarity
                best_match = company
        
        return best_match, best_score


# Example usage
if __name__ == "__main__":
    mapper = CompanyMapper()
    job_data = {
        "job_details": {
            "companyDetails": {
                "name": "Acme Corporation",
                "company": {"entityUrn": "urn:li:fs_normalized_company:12345"},
                "companyUrl": "https://www.acme.com",
                "headquarter": {"city": "San Francisco", "country": "United States"}
            }
        }
    }
    company = mapper.get_or_create_company(job_data)
    print(f"Company: {company.name if company else 'Not found'}")