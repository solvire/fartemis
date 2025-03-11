"""
Controllers for job board operations
@author: solvire
@date: 2025-03-04
"""
import logging
import traceback
from typing import Dict, List, Any, Tuple, Optional
from django.utils import timezone
from django.db import transaction
from datetime import datetime, timedelta

from jobboards.constants import JobSource
from jobboards.factories import JobBoardClientFactory
from jobboards.models import Job, JobSearchQuery
from fartemis.llms.clients import LLMClientFactory
from fartemis.llms.constants import LLMProvider, AnthropicClient


from fartemis.jobboards.models import Job, JobSearchQuery, Technology
from fartemis.jobboards.models import FeedSource, FeedItem, FeedFetchLog
from fartemis.jobboards.clients import FeedClientFactory 
from fartemis.jobboards.clients import (
    BaseFeedItem, FeedAggregator, RSSFeedClient, 
    HackerNewsWhoIsHiringClient, RedditJobBoardClient
)


logger = logging.getLogger(__name__)

class JobBoardController:
    """Controller for job board operations"""
    
    def __init__(self):
        """Initialize controller"""
        self.sources = [
            JobSource.LINKEDIN,
            JobSource.INDEED,
            # Add more sources as they are implemented
        ]
        
    def search(self, query: str, user, **kwargs) -> List[Job]:
        """
        Search for jobs across all configured job boards
        
        Args:
            query: Search query string
            user: User performing the search
            **kwargs: Additional search parameters
            
        Returns:
            List of created/updated Job instances
        """
        all_jobs = []
        
        # Create/update the search query record
        search_query, created = JobSearchQuery.objects.get_or_create(
            query=query,
            user=user,
            defaults={
                'location': kwargs.get('location', ''),
                'remote_only': kwargs.get('remote_only', False),
                'min_salary': kwargs.get('min_salary'),
                'max_salary': kwargs.get('max_salary'),
                'job_level': kwargs.get('job_level', ''),
                'employment_type': kwargs.get('employment_type', ''),
            }
        )
        search_query.last_executed = timezone.now()
        search_query.save()
        
        # Search each job board
        for source in self.sources:
            try:
                client = JobBoardClientFactory.create(source)
                results = client.search_jobs(
                    query=query,
                    location=kwargs.get('location', ''),
                    remote=kwargs.get('remote_only', False),
                    min_salary=kwargs.get('min_salary'),
                    max_salary=kwargs.get('max_salary'),
                    job_level=kwargs.get('job_level', ''),
                    employment_type=kwargs.get('employment_type', '')
                )
                
                # Process results and create/update Job instances
                for job_data in results:
                    job, created = Job.objects.update_or_create(
                        source=source,
                        source_id=job_data['id'],
                        user=user,
                        defaults={
                            'title': job_data['title'],
                            'company_name': job_data['company'],
                            'location': job_data['location'],
                            'remote': job_data.get('remote', False),
                            'description': job_data.get('description', ''),
                            'description_html': job_data.get('description_html', ''),
                            'url': job_data['url'],
                            'posted_date': job_data.get('posted_date'),
                            'expires_date': job_data.get('expires_date'),
                            'salary_min': job_data.get('salary_min'),
                            'salary_max': job_data.get('salary_max'),
                            'salary_currency': job_data.get('salary_currency', 'USD'),
                            'employment_type': job_data.get('employment_type', ''),
                            'job_level': job_data.get('job_level', ''),
                        }
                    )
                    
                    # Add relationship to search query
                    job.search_queries.add(search_query)
                    
                    # Link or create company profile
                    job.link_or_create_company_profile()
                    
                    # Extract keywords and link to technologies
                    self.extract_keywords(job)
                    
                    # Try to enrich company data from job description
                    self.enrich_company_data(job)
                    
                    # Calculate job relevance if it's a new job
                    if created:
                        self.calculate_job_relevance(job, user)
                        
                    all_jobs.append(job)
                    
            except Exception as e:
                # Log the error but continue with other sources
                print(f"Error searching {source}: {str(e)}")
                continue
                
        return all_jobs
        
    def sync_company_data(self, batch_size=50):
        """
        Bulk synchronization of company data
        
        Looks for jobs with company_name but no company_profile and tries to link them
        Also enriches company data where needed
        """
        from django.db.models import Count
        
        # Find the most common company names without profiles
        companies_to_process = Job.objects.filter(
            company_profile__isnull=True
        ).values('company_name').annotate(
            count=Count('id')
        ).order_by('-count')[:batch_size]
        
        processed_count = 0
        
        for company_data in companies_to_process:
            company_name = company_data['company_name']
            
            # Get one job from this company to use as reference
            sample_job = Job.objects.filter(
                company_name=company_name,
                company_profile__isnull=True
            ).first()
            
            if sample_job:
                # Link or create company profile
                company = sample_job.link_or_create_company_profile()
                
                # Enrich company data
                self.enrich_company_data(sample_job)
                
                # Link all other jobs from the same company
                Job.objects.filter(
                    company_name=company_name,
                    company_profile__isnull=True
                ).update(company_profile=company)
                
                processed_count += 1
                
        return processed_count
        
    def calculate_job_relevance(self, job: Job, user) -> float:
        """
        Calculate relevance score for a job based on user profile
        
        Args:
            job: Job instance to score
            user: User to compare against
            
        Returns:
            Relevance score from 0.0 to 1.0
        """
        # Use LLM to calculate relevance
        llm_client = LLMClientFactory.create(LLMProvider.ANTHROPIC)
        
        # Get user profile/resume data
        # Assuming there's a UserProfile model with a resume field
        user_profile = user.profile
        resume_text = user_profile.resume or ""
        
        # Create prompt for LLM
        prompt = f"""
        Given a job description and a user's resume, calculate how relevant this job is for the user on a scale of 0.0 to 1.0.
        
        JOB TITLE: {job.title}
        COMPANY: {job.company}
        JOB DESCRIPTION: {job.description}
        
        USER RESUME: {resume_text}
        
        Analyze the match between the job requirements and the user's skills and experience.
        Return only a number between 0.0 and 1.0, where 1.0 means a perfect match and 0.0 means no match at all.
        """
        
        response = llm_client.complete(prompt)
        
        try:
            # Parse the response to get the score
            score = float(response.strip())
            # Clamp to valid range
            score = max(0.0, min(1.0, score))
            
            # Update job with relevance score
            job.relevance_score = score
            job.save()
            
            return score
        except:
            # Default to 0.5 if parsing fails
            job.relevance_score = 0.5
            job.save()
            return 0.5
            
    def extract_keywords(self, job: Job) -> List[str]:
        """
        Extract important keywords from job description using LLM and link to Technology models
        
        Args:
            job: Job instance to analyze
            
        Returns:
            List of keyword strings
        """
        from companies.models import Technology
        
        llm_client = LLMClientFactory.create(LLMProvider.ANTHROPIC)
        
        prompt = f"""
        Extract the most important skills, technologies, and qualifications from this job description.
        Return them as a comma-separated list of single words or short phrases.
        
        JOB TITLE: {job.title}
        JOB DESCRIPTION: {job.description}
        """
        
        response = llm_client.complete(prompt)
        
        # Parse the response into a list of keywords
        keywords = [kw.strip() for kw in response.split(',') if kw.strip()]
        
        # Update job with keywords
        job.keywords = keywords
        
        # Link to Technology models where possible and create new ones where needed
        for keyword in keywords:
            tech, created = Technology.objects.get_or_create(
                name=keyword,
                defaults={
                    'category': 'Skill',  # Default category
                }
            )
            job.required_skills.add(tech)
            
            # If we have a company profile, link the technology to the company
            if job.company_profile:
                job.company_profile.technologies.get_or_create(technology=tech)
        
        job.save()
        
        return keywords
        
    def enrich_company_data(self, job: Job) -> None:
        """
        Use LLM to enrich company data based on job descriptions
        
        Args:
            job: Job instance to analyze
        """
        # Skip if no company profile is linked
        if not job.company_profile:
            return
            
        # Skip if company already has comprehensive data
        company = job.company_profile
        if (company.description and company.headquarters_city and 
            company.founded_year and company.ai_analysis):
            return
            
        llm_client = LLMClientFactory.create(LLMProvider.ANTHROPIC)
        
        prompt = f"""
        Based on this job description, extract information about the company.
        
        JOB TITLE: {job.title}
        COMPANY NAME: {company.name}
        JOB DESCRIPTION: {job.description}
        
        Please extract and return the following in a structured format:
        1. Company description (1-2 paragraphs summary)
        2. Headquarters location (city, country if mentioned)
        3. Company size (employee range if mentioned)
        4. Founded year (if mentioned)
        5. Primary industry (if mentioned)
        6. Public or private status (if mentioned)
        7. Company culture description (if available)
        
        For each field, if the information is not available in the job description, respond with "Not mentioned".
        """
        
        response = llm_client.complete(prompt)
        
        # Parse the response and update the company profile
        # This is a simple implementation - in production, you'd want more robust parsing
        lines = response.strip().split('\n')
        
        description = None
        hq_city = None
        hq_country = None
        employee_min = None
        employee_max = None
        founded_year = None
        is_public = None
        ai_analysis = response  # Store the full analysis
        
        # Very simple parsing - in production you'd want more robust extraction
        for line in lines:
            if line.startswith('1.') and 'Not mentioned' not in line:
                description = line.replace('1.', '').strip()
            elif line.startswith('2.') and 'Not mentioned' not in line:
                location = line.replace('2.', '').strip()
                if ',' in location:
                    hq_city, hq_country = [x.strip() for x in location.split(',', 1)]
                else:
                    hq_city = location
            elif line.startswith('3.') and 'Not mentioned' not in line:
                size = line.replace('3.', '').strip()
                # Try to extract employee range from text
                import re
                numbers = re.findall(r'\d+', size)
                if len(numbers) >= 2:
                    employee_min = int(numbers[0])
                    employee_max = int(numbers[1])
                elif len(numbers) == 1:
                    if 'over' in size.lower() or 'more than' in size.lower():
                        employee_min = int(numbers[0])
                    else:
                        employee_max = int(numbers[0])
            elif line.startswith('4.') and 'Not mentioned' not in line:
                year_match = re.search(r'\d{4}', line)
                if year_match:
                    founded_year = int(year_match.group(0))
            elif line.startswith('5.') and 'Not mentioned' not in line:
                industry_name = line.replace('5.', '').strip()
                # Link to Industry model
                from companies.models import Industry, CompanyIndustry
                industry, created = Industry.objects.get_or_create(name=industry_name)
                CompanyIndustry.objects.get_or_create(
                    company=company,
                    industry=industry,
                    defaults={'is_primary': True}
                )
            elif line.startswith('6.') and 'Not mentioned' not in line:
                is_public = 'public' in line.lower() and 'private' not in line.lower()
                if is_public:
                    # Try to extract stock symbol if mentioned
                    symbol_match = re.search(r'\(([A-Z]{1,5})\)', line)
                    if symbol_match:
                        company.stock_symbol = symbol_match.group(1)
        
        # Update company fields if we found anything new
        if description and not company.description:
            company.description = description
        if hq_city and not company.headquarters_city:
            company.headquarters_city = hq_city
        if hq_country and not company.headquarters_country:
            company.headquarters_country = hq_country
        if employee_min and not company.employee_count_min:
            company.employee_count_min = employee_min
        if employee_max and not company.employee_count_max:
            company.employee_count_max = employee_max
        if founded_year and not company.founded_year:
            company.founded_year = founded_year
        if is_public is not None and not company.is_public:
            company.is_public = is_public
        if ai_analysis:
            company.ai_analysis = ai_analysis
            
        company.save()


class FeedController:
    """Controller for feed-based job discovery and processing."""
    
    def __init__(self):
        self.aggregator = FeedAggregator()
        self.llm_client = None
    
    def initialize_feed_sources(self) -> int:
        """Initialize feed sources from database."""

        
        sources = FeedSource.objects.filter(is_active=True)
        count = 0
        
        for source in sources:
            try:
                # Use factory to create appropriate client
                client = FeedClientFactory.create(
                    source_type=source.source_type,
                    name=source.name,
                    url=source.url,
                    **source.config  # Pass any additional configuration
                )
                
                if client:
                    self.aggregator.add_client(client)
                    count += 1
                else:
                    logger.warning(f"Could not create client for {source.name} ({source.source_type})")
                    
            except Exception as e:
                logger.error(f"Error initializing feed source {source.name}: {e}")
        
        return count
    
    def fetch_all_sources(self) -> Dict[str, int]:
        """Fetch jobs from all sources and store them."""
        self.initialize_feed_sources()
        results = {}
        
        for client in self.aggregator.feed_clients:
            results[client.name] = self._fetch_source(client.name)
            
        return results
    
    def fetch_source(self, source_name: str) -> int:
        """Fetch jobs from a specific source and store them."""
        self.initialize_feed_sources()
        return self._fetch_source(source_name)
    
    def _fetch_source(self, source_name: str) -> int:
        """Fetch and process a specific feed source."""
        try:
            source = FeedSource.objects.get(name=source_name, is_active=True)
        except FeedSource.DoesNotExist:
            logger.error(f"Feed source not found: {source_name}")
            return 0
        
        # Create fetch log
        fetch_log = FeedFetchLog.objects.create(
            source=source,
            start_time=timezone.now()
        )
        
        try:
            # Find the client
            client = None
            for c in self.aggregator.feed_clients:
                if c.name == source_name:
                    client = c
                    break
            
            if not client:
                raise ValueError(f"Feed client not initialized: {source_name}")
            
            # Fetch items
            items = client.fetch_jobs()
            
            # Store items
            new_items = 0
            with transaction.atomic():
                for item in items:
                    _, created = self._store_feed_item(source, item)
                    if created:
                        new_items += 1
            
            # Update source and log
            source.last_fetched = timezone.now()
            source.save(update_fields=['last_fetched'])
            
            fetch_log.end_time = timezone.now()
            fetch_log.success = True
            fetch_log.items_fetched = len(items)
            fetch_log.items_new = new_items
            fetch_log.save()
            
            logger.info(f"Fetched {len(items)} items from {source_name}, {new_items} new")
            return new_items
            
        except Exception as e:
            logger.error(f"Error fetching {source_name}: {e}")
            logger.error(traceback.format_exc())
            
            fetch_log.end_time = timezone.now()
            fetch_log.success = False
            fetch_log.error_message = str(e)
            fetch_log.save()
            
            return 0
    
    def _store_feed_item(self, source: FeedSource, feed_item: BaseFeedItem) -> Tuple[FeedItem, bool]:
        """Store a feed item, returning (item, created)."""
        # Check if item already exists
        try:
            existing = FeedItem.objects.get(source=source, guid=feed_item.original_guid)
            return existing, False
        except FeedItem.DoesNotExist:
            pass
        
        # Create new item
        item = FeedItem(
            title=feed_item.title,
            description=feed_item.description,
            url=feed_item.url,
            company_name=feed_item.company_name,
            location=feed_item.location,
            posted_date=feed_item.posted_date or timezone.now(),
            source=source,
            guid=feed_item.original_guid,
            raw_data=feed_item.original_data
        )
        item.save()
        
        return item, True
    
    def process_unprocessed_items(self, batch_size: int = 50) -> int:
        """Process unprocessed feed items."""
        items = FeedItem.objects.filter(is_processed=False)[:batch_size]
        processed = 0
        
        for item in items:
            try:
                self.process_feed_item(item)
                processed += 1
            except Exception as e:
                logger.error(f"Error processing feed item {item.id}: {e}")
                logger.error(traceback.format_exc())
        
        return processed
    
    def process_feed_item(self, item: FeedItem) -> FeedItem:
        """Process a feed item to extract info and link companies."""
        try:
            # Link to company profile
            item.link_or_create_company_profile()
            
            # Extract technologies
            item.extract_technologies()
            
            # Convert to job if relevant
            self._convert_to_job(item)
            
            # Mark as processed
            item.is_processed = True
            item.save(update_fields=['is_processed'])
            
            return item
            
        except Exception as e:
            logger.error(f"Error processing feed item {item.id}: {e}")
            logger.error(traceback.format_exc())
            raise
    
    def _convert_to_job(self, item: FeedItem) -> Optional[Job]:
        """Convert feed item to a job if it seems to be a relevant posting."""
        
        # Skip if already linked
        if item.job:
            return item.job
        
        # Check if it seems like a job posting
        job_indicators = ['hiring', 'job', 'position', 'career', 'developer', 'engineer']
        is_job = any(indicator in item.title.lower() for indicator in job_indicators)
        
        if not is_job:
            item.is_relevant = False
            item.save(update_fields=['is_relevant'])
            return None
        
        # Use factory to create job
        return JobFactory.create_from_feed_item(item)
    
    def use_llm_for_enrichment(self, item: FeedItem) -> Dict[str, Any]:
        """Use LLM to extract structured information from job posting."""
        from fartemis.llms.clients import LLMClientFactory
        from fartemis.llms.constants import LLMProvider
        
        if not self.llm_client:
            self.llm_client = LLMClientFactory.create(LLMProvider.ANTHROPIC)
            
        # Prepare prompt
        prompt = f"""
        You are a job posting analyzer. Extract the following information from this job posting:
        
        JOB TITLE: {item.title}
        JOB DESCRIPTION: {item.description[:2000]}...  # Truncate for token limits
        
        Please extract the following information in JSON format:
        1. company_name: The name of the company hiring
        2. location: Where the job is located (remote, office location, etc.)
        3. job_type: Full-time, part-time, contract, etc.
        4. experience_level: Junior, mid-level, senior, etc.
        5. technologies: List of specific technologies, languages, frameworks mentioned
        6. salary_range: If mentioned, the salary range
        7. key_responsibilities: List of main job responsibilities
        8. required_skills: List of explicitly required skills
        9. preferred_skills: List of preferred but not required skills
        10. education_requirements: Any specific education requirements
        11. benefits: Any mentioned benefits or perks
        
        Return only valid JSON without any explanations.
        """
        
        try:
            response = self.llm_client.generate_text(prompt)
            
            # Parse JSON from response
            import json
            import re
            
            # Find JSON object in the response (in case the LLM added explanations)
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                extracted_data = json.loads(json_match.group(0))
            else:
                extracted_data = json.loads(response)
                
            # Store the extracted data
            self._apply_llm_enrichment(item, extracted_data)
            
            return extracted_data
            
        except Exception as e:
            logger.error(f"Error using LLM for job enrichment: {e}")
            return {}
    
    def _apply_llm_enrichment(self, item: FeedItem, data: Dict[str, Any]) -> None:
        """Apply enrichment data from LLM to feed item and related objects."""
        # Update feed item if new info is available
        if data.get('company_name') and not item.company_name:
            item.company_name = data['company_name']
            
        if data.get('location') and not item.location:
            item.location = data['location']
            
        item.raw_data['llm_enrichment'] = data
        item.save()
        
        # Update or create job if it exists
        if item.job:
            job = item.job
            
            # Update job details
            if data.get('job_type'):
                job.job_type = data['job_type']
                
            if data.get('experience_level'):
                job.seniority = data['experience_level']
                
            if data.get('salary_range'):
                job.salary_range = data['salary_range']
                
            job.save()
            
            # Add technologies if found
            if data.get('technologies'):
                self._add_technologies_to_job(job, data['technologies'])
            
            # Add required skills
            if data.get('required_skills'):
                self._add_technologies_to_job(job, data['required_skills'])
        
        # Update company profile if it exists
        if item.company_profile and (data.get('benefits') or data.get('company_name')):
            company = item.company_profile
            
            # Store benefits information
            if data.get('benefits') and 'benefits' not in company.metadata:
                company.metadata['benefits'] = data['benefits']
                company.save()
    
    def _add_technologies_to_job(self, job: Job, tech_names: List[str]) -> None:
        """Add technologies to job based on names."""
        for name in tech_names:
            # Clean and normalize name
            clean_name = name.strip().lower()
            
            # Skip very short names
            if len(clean_name) < 2:
                continue
                
            # Try to find existing technology
            tech, created = Technology.objects.get_or_create(
                name__iexact=clean_name,
                defaults={'name': name}
            )
            
            # Add to job
            job.required_skills.add(tech)
    
    def schedule_fetches(self) -> Dict[str, datetime]:
        """Schedule feed fetches based on intervals."""
        sources = FeedSource.objects.filter(is_active=True)
        scheduled = {}
        
        now = timezone.now()
        
        for source in sources:
            # Calculate next fetch time
            if source.last_fetched:
                interval = timedelta(minutes=source.fetch_interval_minutes)
                next_fetch = source.last_fetched + interval
            else:
                next_fetch = now
                
            if next_fetch <= now:
                # Fetch now
                try:
                    self._fetch_source(source.name)
                    scheduled[source.name] = now
                except Exception as e:
                    logger.error(f"Error scheduling fetch for {source.name}: {e}")
            else:
                scheduled[source.name] = next_fetch
                
        return scheduled
    

class JobFactory:
    """Factory for creating job instances from different sources."""
    
    @staticmethod
    def create_from_feed_item(feed_item: FeedItem, search_query=None) -> Optional[Job]:
        """
        Create a job instance from a feed item.
        
        Args:
            feed_item: The feed item to convert
            search_query: Optional job search query to associate with
            
        Returns:
            Job instance or None if creation fails
        """
        try:
            with transaction.atomic():
                # Create a generic search query if needed
                if not search_query:
                    search_query, _ = JobSearchQuery.objects.get_or_create(
                        query="feed_import",
                        defaults={'user': None}  # Note: may need to use a system user here
                    )
                
                # Create the job
                job = Job.objects.create(
                    title=feed_item.title,
                    description=feed_item.description,
                    company_name=feed_item.company_name or "Unknown",
                    url=feed_item.url,
                    source="feed",
                    company_profile=feed_item.company_profile,
                    posted_date=feed_item.posted_date,
                    status="new"
                )
                
                # Link to search query
                job.search_queries.add(search_query)
                
                # Add technologies from feed item
                if feed_item.technologies.exists():
                    job.required_skills.add(*feed_item.technologies.all())
                
                # Link back to feed item
                feed_item.job = job
                feed_item.save(update_fields=['job'])
                
                return job
                
        except Exception as e:
            logger.error(f"Error creating job from feed item {feed_item.id}: {e}")
            return None
    
    @staticmethod
    def create_from_api_data(api_data: Dict[str, Any], source: str, search_query=None) -> Optional[Job]:
        """
        Create a job instance from API data.
        
        Args:
            api_data: The API data to convert
            source: The source of the data (e.g., 'linkedin', 'indeed')
            search_query: Optional job search query to associate with
            
        Returns:
            Job instance or None if creation fails
        """
        try:
            # Implementation for API data conversion
            # This would handle sources like LinkedIn if API access is obtained later
            pass
            
        except Exception as e:
            logger.error(f"Error creating job from API data: {e}")
            return None
    
    @staticmethod
    def create_from_career_page(page_data: Dict[str, Any], company_profile_id: int, search_query=None) -> Optional[Job]:
        """
        Create a job instance from career page data.
        
        Args:
            page_data: The career page data to convert
            company_profile_id: ID of the company profile
            search_query: Optional job search query to associate with
            
        Returns:
            Job instance or None if creation fails
        """
        try:
            # Implementation for career page data conversion
            # This would handle direct scraping of company career pages
            pass
            
        except Exception as e:
            logger.error(f"Error creating job from career page data: {e}")
            return None