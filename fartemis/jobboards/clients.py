from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional

from django.conf import settings
from jobboards.constants import JobSource


from fartemis.jobboards.exceptions import ClientInitializationException


class BaseJobBoardClient(ABC):
    """
    Abstract base class for job board API clients
    """
    
    def __init__(self, **kwargs):
        self.api_key = kwargs.get('api_key')
        self.base_url = kwargs.get('base_url')
        self.headers = kwargs.get('headers', {})
        
    def set_authentication(self, **kwargs):
        """Set authentication credentials"""
        self.api_key = kwargs.get('api_key', self.api_key)
        self.headers.update(kwargs.get('headers', {}))
        return self
        
    @abstractmethod
    def search_jobs(self, query: str, location: str = '', **kwargs) -> List[Dict[str, Any]]:
        """
        Search for jobs based on query parameters
        
        Args:
            query: Search term (e.g. "python developer")
            location: Location (e.g. "San Francisco, CA")
            **kwargs: Additional parameters specific to the job board
            
        Returns:
            List of job listings as dictionaries
        """
        pass
        
    @abstractmethod
    def get_job_details(self, job_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific job
        
        Args:
            job_id: The ID of the job on the platform
            
        Returns:
            Dictionary with job details
        """
        pass





class JobBoardClientFactory:
    """Factory for creating job board clients"""
    
    @staticmethod
    def create(source: str, **kwargs):
        """
        Create a client for the specified job board
        
        Args:
            source: Job board source from JobSource constants
            **kwargs: Additional parameters for client initialization
            
        Returns:
            Initialized client instance
        """
        if source == JobSource.LINKEDIN:
            return LinkedInClient(
                api_key=settings.LINKEDIN_API_KEY,
                base_url=settings.LINKEDIN_API_BASE_URL,
                **kwargs
            )
            
        # elif source == JobSource.INDEED:
        #     return IndeedClient(
        #         api_key=settings.INDEED_API_KEY,
        #         base_url=settings.INDEED_API_BASE_URL,
        #         publisher_id=settings.INDEED_PUBLISHER_ID,
        #         **kwargs
        #     )
            
        # elif source in [
        #     JobSource.GLASSDOOR, 
        #     JobSource.MONSTER, 
        #     JobSource.WELLFOUND,
        #     JobSource.REMOTE_OK,
        #     JobSource.WE_WORK_REMOTELY,
        #     JobSource.GITHUB_JOBS,
        # ]:
        #     # For job boards without official API access or where we're using
        #     # a common approach, use the GenericJobBoardClient with source-specific config
        #     return GenericJobBoardClient(
        #         source=source,
        #         base_url=getattr(settings, f"{source.upper()}_BASE_URL", None),
        #         **kwargs
        #     )
            
        raise ClientInitializationException(f"No client implementation for {source}")
    

import requests
from typing import Dict, List, Any
from django.conf import settings
from jobboards.clients import BaseJobBoardClient
from jobboards.constants import JobSource, JobLevel, EmploymentType
from datetime import datetime


class LinkedInClient(BaseJobBoardClient):
    """
    Client for LinkedIn Jobs API
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.api_key = kwargs.get('api_key', settings.LINKEDIN_API_KEY)
        self.base_url = kwargs.get('base_url', 'https://api.linkedin.com/v2')
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'X-Restli-Protocol-Version': '2.0.0',
            'Content-Type': 'application/json',
        }
        
    def search_jobs(self, query: str, location: str = '', **kwargs) -> List[Dict[str, Any]]:
        """
        Search for jobs on LinkedIn
        
        Args:
            query: Search term (e.g. "python developer")
            location: Location (e.g. "San Francisco, CA")
            **kwargs: Additional parameters
            
        Returns:
            List of job listings as dictionaries
        """
        endpoint = f"{self.base_url}/jobs/search"
        
        # LinkedIn-specific parameter mapping
        params = {
            'keywords': query,
            'location': location,
        }
        
        # Map employment type
        employment_type = kwargs.get('employment_type', '')
        if employment_type:
            employment_type_map = {
                EmploymentType.FULL_TIME: 'F',
                EmploymentType.PART_TIME: 'P',
                EmploymentType.CONTRACT: 'C',
                EmploymentType.TEMPORARY: 'T',
                EmploymentType.INTERNSHIP: 'I',
                EmploymentType.VOLUNTEER: 'V',
            }
            params['f_JT'] = employment_type_map.get(employment_type)
            
        # Add remote filter if requested
        if kwargs.get('remote', False):
            params['f_WT'] = 2  # LinkedIn's code for remote
            
        # Add experience level filter
        job_level = kwargs.get('job_level', '')
        if job_level:
            level_map = {
                JobLevel.ENTRY: '1',
                JobLevel.ASSOCIATE: '2', 
                JobLevel.MID: '3',
                JobLevel.SENIOR: '4',
                JobLevel.LEAD: '5',
                JobLevel.MANAGER: '5',
                JobLevel.DIRECTOR: '6',
                JobLevel.VP: '6',
                JobLevel.EXECUTIVE: '6',
            }
            params['f_E'] = level_map.get(job_level)
            
        # Make the request
        response = requests.get(endpoint, headers=self.headers, params=params)
        response.raise_for_status()
        
        # Process LinkedIn's response format into our standardized format
        jobs_data = response.json()
        
        results = []
        for item in jobs_data.get('elements', []):
            # Extract the job details
            job_details = self._extract_job_details(item)
            results.append(job_details)
            
        return results
    
    def get_job_details(self, job_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific job
        
        Args:
            job_id: The LinkedIn job ID
            
        Returns:
            Dictionary with job details
        """
        endpoint = f"{self.base_url}/jobs/{job_id}"
        
        response = requests.get(endpoint, headers=self.headers)
        response.raise_for_status()
        
        job_data = response.json()
        return self._extract_job_details(job_data)
    
    def _extract_job_details(self, job_data: Dict) -> Dict[str, Any]:
        """
        Extract relevant job details from LinkedIn's response
        
        Args:
            job_data: Raw job data from LinkedIn API
            
        Returns:
            Standardized job data dictionary
        """
        # This is a simplified example - actual LinkedIn API response format would need
        # to be handled according to their documentation
        
        job_view = job_data.get('jobView', {})
        
        # Extract salary range if available
        salary_min = None
        salary_max = None
        salary_currency = 'USD'
        
        compensation = job_view.get('compensation', {})
        if compensation:
            salary_range = compensation.get('salary', {})
            salary_min = salary_range.get('min')
            salary_max = salary_range.get('max')
            salary_currency = compensation.get('currency', 'USD')
        
        # Map LinkedIn employment type to our constants
        employment_type_map = {
            'FULL_TIME': EmploymentType.FULL_TIME,
            'PART_TIME': EmploymentType.PART_TIME,
            'CONTRACT': EmploymentType.CONTRACT,
            'TEMPORARY': EmploymentType.TEMPORARY,
            'INTERNSHIP': EmploymentType.INTERNSHIP,
            'VOLUNTEER': EmploymentType.VOLUNTEER,
        }
        
        linkedin_job_type = job_view.get('jobType', '')
        employment_type = employment_type_map.get(linkedin_job_type, '')
        
        # Map LinkedIn experience level to our job level constants
        level_map = {
            'ENTRY_LEVEL': JobLevel.ENTRY,
            'ASSOCIATE': JobLevel.ASSOCIATE, 
            'MID_SENIOR': JobLevel.MID,
            'SENIOR': JobLevel.SENIOR,
            'DIRECTOR': JobLevel.DIRECTOR,
            'EXECUTIVE': JobLevel.EXECUTIVE,
        }
        
        linkedin_level = job_view.get('experienceLevel', '')
        job_level = level_map.get(linkedin_level, '')
        
        # Format posted date
        posted_date = None
        if 'listedAt' in job_view:
            posted_timestamp = job_view['listedAt'] / 1000  # Convert LinkedIn milliseconds to seconds
            posted_date = datetime.fromtimestamp(posted_timestamp)
        
        return {
            'id': job_data.get('entityUrn', '').split(':')[-1],
            'title': job_view.get('title', ''),
            'company': job_view.get('companyName', ''),
            'location': job_view.get('location', ''),
            'remote': 'REMOTE' in job_view.get('workplaceType', ''),
            'description': job_view.get('description', ''),
            'description_html': job_view.get('descriptionHtml', ''),
            'url': f"https://www.linkedin.com/jobs/view/{job_data.get('entityUrn', '').split(':')[-1]}",
            'posted_date': posted_date,
            'salary_min': salary_min,
            'salary_max': salary_max,
            'salary_currency': salary_currency,
            'employment_type': employment_type,
            'job_level': job_level,
        }