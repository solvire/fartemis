"""
Mappers for processing job feed data.

This module contains mapper classes for converting raw job data from various sources
into standardized Job objects for the Fartemis system.
"""

import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

from django.db import transaction
from django.utils import timezone

from fartemis.jobboards.models import Job, JobSource, EmploymentType, FeedSource
from fartemis.llms.clients import LLMClientFactory, LLMProvider

logger = logging.getLogger(__name__)


class BaseJobMapper(ABC):
    """
    Abstract base class for job feed mappers.
    
    Mappers are responsible for converting raw job data from various sources
    into standardized Job objects.
    """
    
    def __init__(self, feed_source: Optional[FeedSource] = None, default_user=None):
        """
        Initialize the mapper.
        
        Args:
            feed_source: Optional feed source model instance
            default_user: Optional user to associate with mapped jobs
        """
        self.feed_source = feed_source
        self.default_user = default_user
    
    @abstractmethod
    def map_job(self, job_summary: Dict[str, Any], job_details: Optional[Dict[str, Any]] = None, user=None) -> Optional[Job]:
        """
        Map raw job data to a Job object.
        
        Args:
            job_summary: Basic job data (e.g., from a search result)
            job_details: Detailed job data (e.g., from a job page), if available
            user: Optional user to associate with the job
            
        Returns:
            A Job instance or None if mapping fails
        """
        pass
    
    @abstractmethod
    def extract_skills(self, job_summary: Dict[str, Any], job_details: Optional[Dict[str, Any]] = None) -> List[str]:
        """
        Extract skill names from job data.
        
        Args:
            job_summary: Basic job data
            job_details: Detailed job data, if available
            
        Returns:
            List of skill names mentioned in the job
        """
        pass
    
    def find_existing_job(self, source: str, source_id: str, user=None) -> Optional[Job]:
        """
        Check if a job with the given source and source_id already exists.
        
        Args:
            source: Source platform (e.g., 'linkedin')
            source_id: ID of the job on the source platform
            user: Optional user to filter by
            
        Returns:
            Existing Job or None
        """
        try:
            query = Job.objects.filter(source=source, source_id=source_id)
            if user:
                query = query.filter(user=user)
            return query.first()
        except Exception as e:
            logger.error(f"Error checking for existing job {source}:{source_id}: {e}")
            return None
    
    def extract_html_content(self, description_text: str) -> str:
        """
        Extract or generate HTML content from description text.
        
        Args:
            description_text: Plain text description
            
        Returns:
            HTML formatted description
        """
        # Simple conversion of plain text to HTML
        # For more complex cases, this could be enhanced with markdown conversion
        if not description_text:
            return ""
            
        # Escape HTML characters
        html = description_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        
        # Convert line breaks to <br> tags
        html = html.replace("\n", "<br>")
        
        # Wrap in a div
        html = f"<div>{html}</div>"
        
        return html
    
    def extract_keywords(self, job_title: str, job_description: str) -> List[str]:
        """
        Extract keywords from job title and description.
        
        Args:
            job_title: Job title
            job_description: Job description
            
        Returns:
            List of relevant keywords
        """
        keywords = []
        
        # Extract words from title (excluding common words)
        if job_title:
            # Remove any non-alphanumeric characters and split
            title_words = re.findall(r'\b[A-Za-z0-9]+\b', job_title)
            stop_words = {'and', 'or', 'the', 'in', 'at', 'for', 'to', 'with', 'a', 'an'}
            keywords.extend([word.lower() for word in title_words if len(word) > 2 and word.lower() not in stop_words])
        
        # Add any skills as keywords
        if job_description:
            skills = self.extract_skills({'title': job_title}, {'description': job_description})
            keywords.extend([skill.lower() for skill in skills])
        
        # Remove duplicates and return
        return list(set(keywords))
    
    def extract_salary_info(self, description: str, user=None) -> Dict[str, Any]:
        """
        Extract salary information from a job description using pattern matching
        and LLM-based extraction.
        
        Args:
            description: The job description text to analyze
            user: The user making the request, if applicable
            
        Returns:
            Dict containing extracted salary information
        """
        return extract_salary_info(description, user)


class LinkedInJobMapper(BaseJobMapper):
    """
    Mapper for LinkedIn job data.
    """
    
    def map_job(self, job_summary: Dict[str, Any], job_details: Optional[Dict[str, Any]] = None, user=None) -> Optional[Job]:
        """
        Map LinkedIn job data to a Job object.
        
        Args:
            job_summary: LinkedIn job search result data
            job_details: LinkedIn job details data
            user: Optional user to associate with the job
            
        Returns:
            A Job instance or None if mapping fails
        """
        try:
            # Extract job ID from entityUrn or jobId
            job_id = job_summary.get('jobId', job_summary.get('entityUrn', '').split(':')[-1])
            if not job_id:
                logger.warning("Could not extract job ID from LinkedIn data")
                return None
            
            # Use user param or default user
            user_obj = user or self.default_user
            if not user_obj:
                logger.warning("No user specified for job mapping")
                # Continue without user if not required
            
            # Check if job already exists
            existing_job = self.find_existing_job(JobSource.LINKEDIN, job_id, user_obj)
            if existing_job:
                logger.debug(f"Job already exists: {JobSource.LINKEDIN}:{job_id}")
                return existing_job
            
            # Get basic job info from summary
            title = job_summary.get('title', 'Untitled Job')
            
            # Get detailed info if available
            description = ""
            company_name = ""
            location = ""
            posted_date = None
            raw_data = {}
            apply_url = f"https://www.linkedin.com/jobs/view/{job_id}/"
            remote = False
            
            if job_details:
                # Extract description
                if 'description' in job_details:
                    if isinstance(job_details['description'], dict) and 'text' in job_details['description']:
                        description = job_details['description']['text']
                    else:
                        description = str(job_details['description'])
                
                # Extract company name
                if 'companyDetails' in job_details:
                    company_details = job_details['companyDetails']
                    if isinstance(company_details, dict):
                        # Navigate through possible nested structures
                        if 'com.linkedin.voyager.deco.jobs.web.shared.WebCompactJobPostingCompany' in company_details:
                            company_data = company_details['com.linkedin.voyager.deco.jobs.web.shared.WebCompactJobPostingCompany']
                            if 'companyResolutionResult' in company_data:
                                company_name = company_data['companyResolutionResult'].get('name', '')
                
                # Extract location
                location = job_details.get('formattedLocation', '')
                
                # Extract remote status
                remote = job_details.get('workRemoteAllowed', False)
                
                # Extract posted date (LinkedIn uses milliseconds timestamp)
                posted_timestamp = job_details.get('listedAt', 0)
                if posted_timestamp:
                    try:
                        posted_date = datetime.fromtimestamp(posted_timestamp / 1000.0)
                    except Exception as e:
                        logger.warning(f"Error parsing posted date from {posted_timestamp}: {e}")
                        posted_date = timezone.now()
                
                # Extract apply URL
                if 'applyMethod' in job_details:
                    apply_method = job_details['applyMethod']
                    if isinstance(apply_method, dict):
                        if 'com.linkedin.voyager.jobs.OffsiteApply' in apply_method:
                            apply_data = apply_method['com.linkedin.voyager.jobs.OffsiteApply']
                            if 'companyApplyUrl' in apply_data:
                                apply_url = apply_data['companyApplyUrl']
                
                # Store full details in raw_data
                raw_data = job_details
            
            # Fallback to summary data if needed
            if not title and job_summary.get('title'):
                title = job_summary.get('title')
            
            if not posted_date:
                posted_date = timezone.now()
            
            # Combine summary data with raw_data
            raw_data.update({"job_summary": job_summary})
            
            # Extract skills
            skills = self.extract_skills(job_summary, job_details)
            
            # Extract HTML content
            description_html = self.extract_html_content(description)
            
            # Determine employment type from description or default to full-time
            employment_type = self.extract_employment_type(description)
            
            # Extract keywords
            keywords = self.extract_keywords(title, description)

            # Extract salary info
            salary_info = self.extract_salary_info(description, user_obj)

            logger.info("Looking at salary info")
            logger.info(salary_info)
            
            # Create the job
            with transaction.atomic():
                job = Job.objects.create(
                    title=title,
                    description=description,
                    description_html=description_html,
                    url=apply_url,
                    company_name=company_name,
                    location=location,
                    remote=remote,
                    source=JobSource.LINKEDIN,
                    source_id=job_id,
                    posted_date=posted_date,
                    employment_type=employment_type,
                    required_skills=skills,
                    keywords=keywords,
                    user=user_obj,
                    salary_max=salary_info['salary_max'],
                    salary_min=salary_info['salary_min'],
                    salary_currency=salary_info.get('salary_currency','USD'),
                )
            
            logger.info(f"Created new job: {title} at {company_name}")
            return job
            
        except Exception as e:
            logger.error(f"Error mapping LinkedIn job: {e}")
            return None
    
    def extract_skills(self, job_summary: Dict[str, Any], job_details: Optional[Dict[str, Any]] = None) -> List[str]:
        """
        Extract skill names from LinkedIn job data.
        
        Args:
            job_summary: LinkedIn job search result data
            job_details: LinkedIn job details data
            
        Returns:
            List of skill names mentioned in the job
        """
        skills = []
        
        try:
            # Technology extraction logic
            if job_details and 'description' in job_details:
                description_text = ""
                if isinstance(job_details['description'], dict) and 'text' in job_details['description']:
                    description_text = job_details['description']['text']
                else:
                    description_text = str(job_details['description'])
                
                # Simple keyword extraction for common skills
                # This could be enhanced with NLP or a more comprehensive list
                common_skills = [
                    'Python', 'Java', 'JavaScript', 'TypeScript', 'C++', 'C#', 'Go', 'Rust',
                    'React', 'Angular', 'Vue', 'Node.js', 'Django', 'Flask', 'Spring',
                    'AWS', 'Azure', 'GCP', 'Kubernetes', 'Docker', 'Terraform',
                    'SQL', 'NoSQL', 'MongoDB', 'PostgreSQL', 'MySQL', 'Redis',
                    'TensorFlow', 'PyTorch', 'Scikit-learn', 'Machine Learning', 'AI',
                    'REST', 'GraphQL', 'Microservices', 'Serverless',
                    'Git', 'CI/CD', 'Jenkins', 'GitHub Actions'
                ]
                
                for skill in common_skills:
                    pattern = r'\b' + re.escape(skill) + r'\b'
                    if re.search(pattern, description_text, re.IGNORECASE):
                        skills.append(skill)
                
                # Check for specific skills section
                if 'skills' in job_details and isinstance(job_details['skills'], list):
                    for skill in job_details['skills']:
                        if isinstance(skill, dict) and 'name' in skill:
                            skills.append(skill['name'])
            
            # Try to extract from job title as well
            if job_summary and 'title' in job_summary:
                title = job_summary['title']
                # Look for skills in the job title
                title_words = title.split()
                for word in title_words:
                    word = word.strip(',.()[]{}').lower()
                    if word in [skill.lower() for skill in ['Python', 'Java', 'React', 'AWS', 'Azure', 'GCP']]:
                        skills.append(word.capitalize())
        
        except Exception as e:
            logger.warning(f"Error extracting skills: {e}")
        
        # Remove duplicates and return
        return list(set(skills))
    
    def extract_employment_type(self, description: str) -> str:
        """
        Extract employment type from job description.
        
        Args:
            description: Job description text
            
        Returns:
            Employment type code
        """
        description = description.lower()
        
        # Map LinkedIn employment types to our model's types
        if "part-time" in description or "part time" in description:
            return EmploymentType.PART_TIME
        elif "contract" in description or "contractor" in description:
            return EmploymentType.CONTRACT
        elif "temporary" in description or "temp" in description:
            return EmploymentType.TEMPORARY
        elif "internship" in description or "intern" in description:
            return EmploymentType.INTERNSHIP
        elif "volunteer" in description:
            return EmploymentType.VOLUNTEER
        else:
            # Default to full-time
            return EmploymentType.FULL_TIME
        


### SALARY EXTRACTION ###


def extract_salary_info(description: str, user=None) -> Dict[str, Any]:
    """
    Extract salary information from a job description using pattern matching
    and LLM-based extraction.
    
    Args:
        description (str): The job description text to analyze
        user (User, optional): The user making the request, if applicable
        
    Returns:
        Dict containing extracted salary information:
        {
            'has_salary': bool,
            'salary_min': float or None,
            'salary_max': float or None,
            'salary_currency': str or USD,
            'salary_period': str or None,  # 'yearly', 'monthly', 'hourly', etc.
            'confidence': float,  # 0.0 to 1.0
            'raw_match': str or None  # The text that was matched
        }
    """
    # Default return structure
    result = {
        'has_salary': False,
        'salary_min': None,
        'salary_max': None, 
        'salary_currency': 'USD',
        'salary_period': None,
        'confidence': 0.0,
        'raw_match': None
    }
    
    if not description or len(description.strip()) == 0:
        return result
    
    # First try pattern matching for common salary formats
    pattern_result = _extract_salary_with_patterns(description)
    
    if pattern_result['has_salary'] and pattern_result['confidence'] > 0.8:
        # High confidence match with regex, return without using LLM
        return pattern_result
    
    # If no clear match or low confidence, use LLM for extraction
    try:
        llm_result = _extract_salary_with_llm(description, user)
        
        # If pattern matching found something but LLM has higher confidence, use LLM result
        if (pattern_result['confidence'] < llm_result['confidence'] or 
            not pattern_result['has_salary']):
            return llm_result
        
        # Otherwise use pattern result
        return pattern_result
        
    except Exception as e:
        logger.error(f"Error extracting salary with LLM: {str(e)}")
        # Fall back to pattern matching result if LLM fails
        return pattern_result


def _extract_salary_with_patterns(description: str) -> Dict[str, Any]:
    """
    Extract salary information using regex pattern matching.
    """
    result = {
        'has_salary': False,
        'salary_min': None,
        'salary_max': None, 
        'salary_currency': 'USD',
        'salary_period': None,
        'confidence': 0.0,
        'raw_match': None
    }
    
    # Common currency symbols and their corresponding currencies
    currency_symbols = {
        '$': 'USD',
        '€': 'EUR',
        '£': 'GBP',
        '¥': 'JPY',
        '₹': 'INR',
        'A$': 'AUD',
        'C$': 'CAD',
        'CHF': 'CHF',
        'NZ$': 'NZD',
    }
    
    # Pattern for matching salary ranges with currency symbols
    # For example: "$80,000 - $120,000" or "$80k-$120k" or "$80,000 to $120,000"
    salary_range_pattern = r'(?P<currency>[A-Z]{3}|\$|€|£|¥|₹|A\$|C\$|CHF|NZ\$)\s*(?P<min>[\d,.]+[k]?)\s*(?:-|to|–)\s*(?P<currency2>[A-Z]{3}|\$|€|£|¥|₹|A\$|C\$|CHF|NZ\$)?\s*(?P<max>[\d,.]+[k]?)'
    
    # Alternative pattern for single salary values
    # For example: "up to $120,000" or "from $80,000"
    single_salary_pattern = r'(?:up to|from|starting at|minimum)\s+(?P<currency>[A-Z]{3}|\$|€|£|¥|₹|A\$|C\$|CHF|NZ\$)\s*(?P<amount>[\d,.]+[k]?)'
    
    # Period identifiers
    period_keywords = {
        'year': 'yearly',
        'annual': 'yearly',
        'annually': 'yearly',
        'month': 'monthly',
        'hour': 'hourly',
        'day': 'daily',
        'week': 'weekly',
    }
    
    # Search for salary ranges
    match = re.search(salary_range_pattern, description, re.IGNORECASE)
    
    if match:
        result['raw_match'] = match.group(0)
        result['has_salary'] = True
        
        # Process currency
        currency_symbol = match.group('currency')
        result['salary_currency'] = currency_symbols.get(currency_symbol, currency_symbol)
        
        # Process min and max values
        min_value = match.group('min')
        max_value = match.group('max')
        
        # Convert k notation to full numbers
        min_value = _convert_k_notation(min_value)
        max_value = _convert_k_notation(max_value)
        
        result['salary_min'] = min_value
        result['salary_max'] = max_value
        
        # Look for period indicators near the match
        context = description[max(0, match.start()-30):min(len(description), match.end()+30)]
        for keyword, period in period_keywords.items():
            if re.search(r'\b' + keyword + r'\b', context, re.IGNORECASE):
                result['salary_period'] = period
                break
                
        if not result['salary_period']:
            # Default to yearly if no period is specified
            result['salary_period'] = 'yearly'
            
        result['confidence'] = 0.9  # High confidence for well-formed ranges
        return result
    
    # If no range found, try single salary patterns
    match = re.search(single_salary_pattern, description, re.IGNORECASE)
    
    if match:
        result['raw_match'] = match.group(0)
        result['has_salary'] = True
        
        # Process currency
        currency_symbol = match.group('currency')
        result['salary_currency'] = currency_symbols.get(currency_symbol, currency_symbol)
        
        # Process the amount
        amount = match.group('amount')
        amount = _convert_k_notation(amount)
        
        # Determine if it's min or max based on the prefix
        prefix = match.group(0).split()[0].lower()
        if prefix in ['up', 'maximum']:
            result['salary_max'] = amount
        else:  # 'from', 'starting', 'minimum'
            result['salary_min'] = amount
            
        # Look for period indicators
        context = description[max(0, match.start()-30):min(len(description), match.end()+30)]
        for keyword, period in period_keywords.items():
            if re.search(r'\b' + keyword + r'\b', context, re.IGNORECASE):
                result['salary_period'] = period
                break
                
        if not result['salary_period']:
            # Default to yearly if no period is specified
            result['salary_period'] = 'yearly'
            
        result['confidence'] = 0.7  # Lower confidence for single values
        return result
    
    return result


def _extract_salary_with_llm(description: str, user=None) -> Dict[str, Any]:
    """
    Extract salary information using the LLM.
    
    Args:
        description (str): The job description text
        user (User, optional): The user making the request, if applicable
        
    Returns:
        Dict with the extracted salary information
    """
    result = {
        'has_salary': False,
        'salary_min': None,
        'salary_max': None, 
        'salary_currency': None,
        'salary_period': None,
        'confidence': 0.0,
        'raw_match': None
    }
    
    # Create LLM client
    llm_client = LLMClientFactory.create(LLMProvider.ANTHROPIC)
    
    # Prepare prompt
    prompt = f"""
You are a salary extraction expert. Extract salary information from the following job description. 
Pay special attention to phrases like "Pay Range:", "Salary Range:", "Compensation Range:", etc.

Return ONLY a JSON object with the following structure:
{{
  "has_salary": true or false,
  "salary_min": minimum salary as a number (no commas, currency symbols, or 'k'), or null if not found,
  "salary_max": maximum salary as a number (no commas, currency symbols, or 'k'), or null if not found,
  "salary_currency": three-letter currency code (e.g., "USD", "EUR"), or null if not found,
  "salary_period": "hourly", "daily", "weekly", "monthly", "yearly", or null if not found,
  "confidence": a number between 0.0 and 1.0 indicating your confidence in the extraction,
  "raw_match": the exact text that contains the salary information, or null if not found
}}

Pay special attention to explicitly labeled salary information. 
Ignore any mentions of year ranges (like "1-2 years") that are not salary-related.

Job Description:
{description}
"""

    # Call the LLM
    try:
        response = llm_client.complete(prompt, max_tokens=500, temperature=0.0)
        response_text = response.get('text', '').strip()
        
        # Extract JSON from response (handling potential non-JSON text)
        import json
        import re
        
        # Try to find JSON object in the response
        json_match = re.search(r'({[\s\S]*})', response_text)
        if json_match:
            json_str = json_match.group(1)
            extracted_data = json.loads(json_str)
            
            # Validate the extracted data
            if 'has_salary' in extracted_data:
                # Convert string number values to actual numbers
                if extracted_data.get('salary_min'):
                    try:
                        extracted_data['salary_min'] = float(extracted_data['salary_min'])
                    except (ValueError, TypeError):
                        extracted_data['salary_min'] = None
                        
                if extracted_data.get('salary_max'):
                    try:
                        extracted_data['salary_max'] = float(extracted_data['salary_max'])
                    except (ValueError, TypeError):
                        extracted_data['salary_max'] = None
                
                # Update result with extracted data
                result.update(extracted_data)
                
                # If LLM found salary but didn't set confidence, set a default
                if result['has_salary'] and result['confidence'] == 0.0:
                    result['confidence'] = 0.8
                    
                return result
        
        # If we couldn't parse the JSON or it's not in the expected format
        logger.warning(f"Could not parse LLM response as valid salary JSON: {response_text}")
        return result
        
    except Exception as e:
        logger.error(f"Error calling LLM for salary extraction: {str(e)}")
        return result


def _convert_k_notation(value_str: str) -> float:
    """
    Convert a string value with possible 'k' notation to a float.
    
    Examples:
        "80k" -> 80000.0
        "80,000" -> 80000.0
        "80" -> 80.0
    """
    if not value_str:
        return None
        
    # Remove any commas and currency symbols
    value_str = value_str.replace(',', '').replace('$', '').replace('€', '').replace('£', '')
    
    # Check for 'k' notation
    if value_str.lower().endswith('k'):
        value_str = value_str[:-1]
        try:
            return float(value_str) * 1000
        except ValueError:
            return None
    
    # Regular number
    try:
        return float(value_str)
    except ValueError:
        return None