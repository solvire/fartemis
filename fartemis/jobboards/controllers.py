"""
Controllers for job board operations
@author: solvire
@date: 2025-03-04
"""
from typing import Dict, List, Any
from django.utils import timezone
from jobboards.constants import JobSource
from jobboards.factories import JobBoardClientFactory
from jobboards.models import Job, JobSearchQuery
from fartemis.llms.clients import LLMClientFactory
from fartemis.llms.constants import LLMProvider


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
