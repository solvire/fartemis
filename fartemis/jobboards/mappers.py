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
                    user=user_obj
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