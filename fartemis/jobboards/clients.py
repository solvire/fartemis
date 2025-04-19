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



class ZyteClient(BaseAPIClient):
    """
    Client for Zyte API
    """
    
    def __init__(self, **kwargs):
        self.api_key = kwargs.get('api_key')
        self.base_url = kwargs.get('base_url', 'https://api.zyte.com/v1')
        self.use_mock_data = kwargs.get('use_mock_data', False)
        
        # If credentials are provided at init, set them
        if self.api_key:
            self.set_authentication(api_key=self.api_key, base_url=self.base_url)
    
    def set_authentication(self, **kwargs):
        """
        Set authentication for Zyte API
        
        Args:
            api_key: Zyte API key
            base_url: Base URL for API
        """
        if "base_url" in kwargs:
            self.base_url = kwargs["base_url"]
            
        if "api_key" in kwargs:
            self.api_key = kwargs["api_key"]
            # Zyte uses basic auth with empty password
            self.auth = (self.api_key, '')
        else:
            raise ValueError("api_key is required for Zyte authentication")
            
        logger.info(f"Zyte client authenticated with base URL: {self.base_url}")
        return self
        
    def check_credentials(self) -> dict:
        """
        Verify Zyte credentials by making a test API call
        
        Returns:
            dict: Account info if successful, None if failed
        """
        logger.info("Checking credentials for Zyte")
        
        if self.use_mock_data:
            logger.warning("Using mock data - skipping credentials check")
            return {"status": "mock_authenticated"}
            
        try:
            # Make a simple API call to verify credentials
            test_payload = {
                "url": "https://example.com",
                "httpResponseBody": True
            }
            
            response = requests.post(
                f"{self.base_url}/extract",
                auth=self.auth,
                json=test_payload
            )
            
            if response.status_code == 200:
                return {"status": "authenticated"}
            else:
                logger.error(f"Zyte authentication failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to authenticate with Zyte: {str(e)}")
            return None
            
    def search_jobs(self, query: str, location: str = '', **kwargs) -> List[Dict[str, Any]]:
        """
        Search for jobs using Zyte API
        
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
            
        # For job search, we need to find a job board URL first
        job_board_url = f"https://www.linkedin.com/jobs/search?keywords={query}&location={location}"
        
        # Use Zyte API to extract job listings
        payload = {
            "url": job_board_url,
            "browserHtml": True,
            "jobPosting": True
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/extract",
                auth=self.auth,
                json=payload
            )
            
            response.raise_for_status()
            data = response.json()
            
            # Process job listings from the response
            results = []
            job_postings = data.get('jobPosting', {}).get('results', [])
            
            for job in job_postings:
                job_details = self._extract_job_details(job)
                results.append(job_details)
                
            return results
            
        except Exception as e:
            logger.error(f"Zyte job search failed: {str(e)}")
            return []
            
    def find_linkedin_profile(self, first_name: str, last_name: str, company_name: str = None) -> Dict[str, Any]:
        """
        Find a LinkedIn profile for a person
        
        This is a multi-step process:
        1. Use Google search via Zyte to find potential LinkedIn profiles
        2. Visit and extract information from the most relevant profile
        
        Args:
            first_name: Person's first name
            last_name: Person's last name
            company_name: Optional company name for better targeting
            
        Returns:
            Dictionary with profile information or empty dict if not found
        """
        # If using mock data, return fake results
        if self.use_mock_data:
            return self._get_mock_linkedin_profile(first_name, last_name, company_name)
        
        # Step 1: Use Google search to find LinkedIn profile
        search_query = f"{first_name} {last_name}"
        if company_name:
            search_query += f" {company_name}"
        search_query += " site:linkedin.com/in/"
        
        search_url = f"https://www.google.com/search?q={search_query}"
        
        try:
            # Request Google search results
            search_payload = {
                "url": search_url,
                "browserHtml": True
            }
            
            search_response = requests.post(
                f"{self.base_url}/extract",
                auth=self.auth,
                json=search_payload
            )
            
            search_response.raise_for_status()
            search_data = search_response.json()
            
            # Parse the HTML to find LinkedIn profile URLs
            html_content = search_data.get("browserHtml", "")
            
            # Use regular expressions to find LinkedIn profile URLs
            import re
            linkedin_pattern = r'https?://(?:www\.)?linkedin\.com/in/[a-zA-Z0-9_-]+'
            linkedin_urls = re.findall(linkedin_pattern, html_content)
            
            if not linkedin_urls:
                logger.info(f"No LinkedIn profile URLs found for {first_name} {last_name}")
                return {}
            
            # Step 2: Extract data from the most relevant profile
            profile_url = linkedin_urls[0]
            
            # Request profile data
            profile_payload = {
                "url": profile_url,
                "browserHtml": True
            }
            
            profile_response = requests.post(
                f"{self.base_url}/extract",
                auth=self.auth,
                json=profile_payload
            )
            
            profile_response.raise_for_status()
            profile_data = profile_response.json()
            
            # Extract profile information from HTML
            html_content = profile_data.get("browserHtml", "")
            
            # Extract basic profile information
            # This is a simplified approach - production code would need more robust parsing
            name_match = re.search(r'<title>(.*?)\s*\|\s*LinkedIn</title>', html_content)
            name = name_match.group(1) if name_match else f"{first_name} {last_name}"
            
            title_match = re.search(r'<h2[^>]*class="[^"]*mt1[^"]*"[^>]*>(.*?)</h2>', html_content)
            title = title_match.group(1) if title_match else ""
            
            # Clean up title from HTML
            if title:
                title = re.sub(r'<[^>]+>', '', title).strip()
            
            # Extract handle from URL
            handle = profile_url.split("/in/")[1].split("/")[0].split("?")[0]
            
            return {
                "url": profile_url,
                "handle": handle,
                "name": name,
                "title": title,
                "source": JobSource.ZYTE
            }
            
        except Exception as e:
            logger.error(f"Error finding LinkedIn profile: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {}
    
    def _get_mock_search_results(self, query: str, location: str = '', **kwargs) -> List[Dict[str, Any]]:
        """Generate mock search results for testing"""
        logger.warning("Using mock data for Zyte job search")
        
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
                'source': JobSource.ZYTE,
            })
            
        return results
        
    def _get_mock_job_details(self, job_url: str) -> Dict[str, Any]:
        """Generate mock job details for testing"""
        logger.warning("Using mock data for Zyte job details")
        
        job_id = job_url.split("/")[-1]
        
        return {
            'id': job_id,
            'title': "Software Developer",
            'company': "Mock Company",
            'location': "San Francisco, CA",
            'remote': True,
            'description': "This is a detailed mock job description.",
            'description_html': "<p>This is a detailed mock job description.</p>",
            'url': job_url,
            'posted_date': None,
            'source': JobSource.ZYTE,
        }
        
    def _get_mock_linkedin_profile(self, first_name: str, last_name: str, company_name: str = None) -> Dict[str, Any]:
        """Generate mock LinkedIn profile data for testing"""
        logger.warning("Using mock data for Zyte LinkedIn profile search")
        
        handle = f"{first_name.lower()}{last_name.lower()}"
        
        return {
            'url': f"https://www.linkedin.com/in/{handle}/",
            'handle': handle,
            'name': f"{first_name} {last_name}",
            'title': "Software Engineer",
            'company': company_name or "Tech Company",
            'location': "San Francisco Bay Area",
            'source': JobSource.ZYTE
        }



class JobBoardClientFactory:
    """Factory for creating job board clients"""
    
    @staticmethod
    def create(client_name, **kwargs):
        """
        Create and return a client for the specified job board
        
        Args:
            client_name: Name of the job board ('linkedin', 'indeed', 'zyte', etc.)
            **kwargs: Additional parameters for client initialization
            
        Returns:
            Initialized client instance
            
        Raises:
            ValueError: If no client implementation exists for the client_name
        """
        # Use mock data in development by default
        use_mock = kwargs.get('use_mock_data', settings.MOCK_DATA)
        
        if client_name == 'linkedin':
            client = LinkedInClient(
                api_key=settings.LINKEDIN_CLIENT_KEY,
                base_url=getattr(settings, 'LINKEDIN_API_BASE_URL', 'https://api.linkedin.com/v2'),
                use_mock_data=use_mock,
                **kwargs
            )
            return client
            
        elif client_name == 'zyte':
            client = ZyteClient(
                api_key=settings.ZYTE_API_KEY,
                base_url=getattr(settings, 'ZYTE_API_BASE_URL', 'https://api.zyte.com/v1'),
                use_mock_data=use_mock,
                **kwargs
            )
            return client
            
        # Additional clients would be added here
            
        raise ValueError(f"No client implementation for {client_name}")

