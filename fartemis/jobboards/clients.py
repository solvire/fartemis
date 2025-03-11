import requests
import logging
from datetime import datetime
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional

from django.conf import settings
from django.utils import timezone

from jobboards.constants import JobSource, JobLevel, EmploymentType

logger = logging.getLogger(__name__)


from fartemis.jobboards.exceptions import ClientInitializationException

class BaseAPIClient(ABC):
    """
    A base client for communicating with an API
    """

    auth_token = None
    username = None
    password = None
    base_url = None
    headers = {
        "Content-Type": "application/json",
        "Content-Accept": "application/json",
        "User-Agent": "Fartemis/1.0"
    }

    @abstractmethod
    def set_authentication(self, **kwargs):
        """
        Used to set authentication credentials
        """
        pass

    @abstractmethod
    def check_credentials(self) -> dict:
        """
        Verify that the credentials are valid
        """
        pass


class LinkedInClient(BaseAPIClient):
    """
    Client for LinkedIn Jobs API
    """
    
    def __init__(self, **kwargs):
        self.api_key = kwargs.get('api_key')
        self.base_url = kwargs.get('base_url', 'https://api.linkedin.com/v2')
        self.use_mock_data = kwargs.get('use_mock_data', False)
        
        # If credentials are provided at init, set them
        if self.api_key:
            self.set_authentication(api_key=self.api_key, base_url=self.base_url)
            
    def set_authentication(self, **kwargs):
        """
        Set authentication for LinkedIn API
        
        Args:
            api_key: LinkedIn API key/token
            base_url: Base URL for API
        """
        if "base_url" in kwargs:
            self.base_url = kwargs["base_url"]
            
        if "api_key" in kwargs:
            self.auth_token = kwargs["api_key"]
            self.headers.update({
                "Authorization": f"Bearer {self.auth_token}",
                "X-Restli-Protocol-Version": "2.0.0"
            })
        else:
            raise ValueError("api_key is required for LinkedIn authentication")
            
        logger.info(f"LinkedIn client authenticated with base URL: {self.base_url}")
        return self
        
    def check_credentials(self) -> dict:
        """
        Verify LinkedIn credentials by making a test API call
        
        Returns:
            dict: Account info if successful, None if failed
        """
        logger.info("Checking credentials for LinkedIn")
        
        if self.use_mock_data:
            logger.warning("Using mock data - skipping credentials check")
            return {"status": "mock_authenticated"}
            
        try:
            # Make a simple API call to verify credentials
            # Using /me endpoint to get basic profile info
            response = requests.get(
                f"{self.base_url}/me",
                headers=self.headers
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"LinkedIn authentication failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to authenticate with LinkedIn: {str(e)}")
            return None
            
    def search_jobs(self, query: str, location: str = '', **kwargs) -> List[Dict[str, Any]]:
        """
        Search for jobs on LinkedIn
        
        Args:
            query: Search term (e.g. "python developer")
            location: Location (e.g. "San Francisco, CA")
            **kwargs: Additional parameters
            
        Returns:
            List of job listings
        """
        # If using mock data, return fake results
        if self.use_mock_data:
            return self._get_mock_search_results(query, location, **kwargs)
            
        # Set up API endpoint and parameters
        endpoint = f"{self.base_url}/jobsearch"
        
        params = {
            'keywords': query,
            'location': location,
            'start': kwargs.get('start', 0),
            'count': kwargs.get('count', 20),
        }
        
        # Add remote filter if requested
        if kwargs.get('remote', False):
            params['remoteFilter'] = 'true'
            
        # Add job level if specified
        if kwargs.get('job_level'):
            params['experienceLevels'] = kwargs.get('job_level')
            
        # Add employment type if specified
        if kwargs.get('employment_type'):
            params['jobType'] = kwargs.get('employment_type')
            
        try:
            # Make the API request
            response = requests.get(
                endpoint,
                headers=self.headers,
                params=params
            )
            
            response.raise_for_status()
            jobs_data = response.json()
            
            # Process and standardize job data
            results = []
            for item in jobs_data.get('elements', []):
                job_details = self._extract_job_details(item)
                results.append(job_details)
                
            return results
            
        except Exception as e:
            logger.error(f"LinkedIn job search failed: {str(e)}")
            # Return empty list rather than raising exception
            return []
            
    def get_job_details(self, job_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific job
        
        Args:
            job_id: The LinkedIn job ID
            
        Returns:
            Dictionary with job details
        """
        # If using mock data, return fake results
        if self.use_mock_data:
            return self._get_mock_job_details(job_id)
            
        endpoint = f"{self.base_url}/jobs/{job_id}"
        
        try:
            response = requests.get(
                endpoint,
                headers=self.headers
            )
            
            response.raise_for_status()
            job_data = response.json()
            
            return self._extract_job_details(job_data)
            
        except Exception as e:
            logger.error(f"LinkedIn job details request failed: {str(e)}")
            return {}
            
    def _extract_job_details(self, job_data: Dict) -> Dict[str, Any]:
        """
        Extract job details from LinkedIn's API response format
        
        Args:
            job_data: Raw API response data
            
        Returns:
            Standardized job data
        """
        # Implementation will depend on LinkedIn's actual API response format
        # This is a placeholder implementation
        
        job_id = job_data.get('id', '')
        if not job_id and 'entityUrn' in job_data:
            # Extract ID from URN
            job_id = job_data['entityUrn'].split(':')[-1]
            
        job_view = job_data.get('jobView', job_data)
        
        return {
            'id': job_id,
            'title': job_view.get('title', ''),
            'company': job_view.get('companyName', ''),
            'location': job_view.get('location', ''),
            'remote': 'remote' in job_view.get('workplaceType', '').lower(),
            'description': job_view.get('description', ''),
            'description_html': job_view.get('descriptionHtml', ''),
            'url': f"https://www.linkedin.com/jobs/view/{job_id}",
            'posted_date': job_view.get('listedAt'),
        }
        
    def _get_mock_search_results(self, query: str, location: str = '', **kwargs) -> List[Dict[str, Any]]:
        """Generate mock search results for testing"""
        logger.warning("Using mock data for LinkedIn job search")
        
        # Generate 3 mock results
        results = []
        for i in range(3):
            results.append({
                'id': f"{i+1000}",
                'title': f"{query.title()} Developer",
                'company': f"Mock Company {i+1}",
                'location': location or "Remote, US",
                'remote': i % 2 == 0,
                'description': f"This is a mock job description for a {query} position.",
                'description_html': f"<p>This is a mock job description for a {query} position.</p>",
                'url': f"https://www.linkedin.com/jobs/view/{i+1000}",
                'posted_date': None,
            })
            
        return results
        
    def _get_mock_job_details(self, job_id: str) -> Dict[str, Any]:
        """Generate mock job details for testing"""
        logger.warning("Using mock data for LinkedIn job details")
        
        return {
            'id': job_id,
            'title': "Software Developer",
            'company': "Mock Company",
            'location': "San Francisco, CA",
            'remote': True,
            'description': "This is a detailed mock job description.",
            'description_html': "<p>This is a detailed mock job description.</p>",
            'url': f"https://www.linkedin.com/jobs/view/{job_id}",
            'posted_date': None,
        }


class JobBoardClientFactory:
    """Factory for creating job board clients"""
    
    @staticmethod
    def create(client_name, **kwargs):
        """
        Create and return a client for the specified job board
        
        Args:
            client_name: Name of the job board ('linkedin', 'indeed', etc.)
            **kwargs: Additional parameters for client initialization
            
        Returns:
            Initialized client instance
            
        Raises:
            ValueError: If no client implementation exists for the client_name
        """
        # Use mock data in development by default
        use_mock = kwargs.get('use_mock_data', settings.DEBUG)
        
        if client_name == 'linkedin':
            client = LinkedInClient(
                api_key=settings.LINKEDIN_CLIENT_KEY,
                base_url=getattr(settings, 'LINKEDIN_API_BASE_URL', 'https://api.linkedin.com/v2'),
                use_mock_data=use_mock,
                **kwargs
            )
            return client
            
        # Additional clients would be added here
            
        raise ValueError(f"No client implementation for {client_name}")