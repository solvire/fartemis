"""

"""
from django.utils.translation import gettext_lazy as _
from django.db import models
from django.utils import timezone
from django.conf import settings

from fartemis.inherits.models import BaseIntModel
from fartemis.jobboards.constants import JobSource, JobStatus, JobLevel, EmploymentType

from fartemis.companies.models import CompanyProfile, Technology


class JobSearchQuery(BaseIntModel):
    """Model for tracking job search queries"""
    query = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True)
    remote_only = models.BooleanField(default=False)
    min_salary = models.IntegerField(null=True, blank=True)
    max_salary = models.IntegerField(null=True, blank=True)
    job_level = models.CharField(max_length=50, choices=JobLevel.CHOICES, blank=True)
    employment_type = models.CharField(max_length=50, choices=EmploymentType.CHOICES, blank=True)
    # Add related_name to avoid clashes
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='jobboard_search_queries')
    last_executed = models.DateTimeField(null=True, blank=True)
    
    def execute(self):
        """Execute this query across all job boards and update last_executed"""
        from jobboards.controllers import JobBoardController
        controller = JobBoardController()
        results = controller.search(
            query=self.query, 
            location=self.location,
            remote_only=self.remote_only,
            min_salary=self.min_salary,
            max_salary=self.max_salary,
            job_level=self.job_level,
            employment_type=self.employment_type
        )
        self.last_executed = timezone.now()
        self.save()
        return results


class Job(BaseIntModel):
    """Model for job listings"""
    title = models.CharField(max_length=255)
    # Reference to CompanyProfile with correct import path
    company_profile = models.ForeignKey(
        'companies.CompanyProfile',  # Make sure companies app is in INSTALLED_APPS
        on_delete=models.CASCADE,
        related_name='job_listings',
        null=True,  # Allow null for jobs where we don't have a company profile yet
    )
    # Keep raw company name from job board for when we don't have a profile
    company_name = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True)
    remote = models.BooleanField(default=False)
    description = models.TextField()
    description_html = models.TextField(blank=True)
    url = models.URLField()
    source = models.CharField(max_length=50, choices=JobSource.CHOICES)
    source_id = models.CharField(max_length=255, blank=True, 
                              help_text="ID of the job on the source platform")
    posted_date = models.DateTimeField(null=True, blank=True)
    expires_date = models.DateTimeField(null=True, blank=True)
    salary_min = models.IntegerField(null=True, blank=True)
    salary_max = models.IntegerField(null=True, blank=True)
    salary_currency = models.CharField(max_length=3, default="USD")
    employment_type = models.CharField(max_length=50, choices=EmploymentType.CHOICES, blank=True)
    job_level = models.CharField(max_length=50, choices=JobLevel.CHOICES, blank=True)
    status = models.CharField(max_length=50, choices=JobStatus.CHOICES, default=JobStatus.NEW)
    relevance_score = models.FloatField(default=0.0, 
                                     help_text="Score from 0-1 indicating relevance to user profile")
    search_queries = models.ManyToManyField('jobboards.JobSearchQuery', related_name='jobs')
    keywords = models.JSONField(default=list, blank=True)
    # Fix Technology model reference and add related_name
    required_skills = models.ManyToManyField('companies.Technology', related_name='required_by_jobs', blank=True)
    # Add related_name to avoid clashes
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='jobboard_jobs')
    
    class Meta:
        unique_together = ('source', 'source_id', 'user')
        indexes = [
            models.Index(fields=['source', 'source_id']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', 'relevance_score']),
            models.Index(fields=['company_name']),
        ]



class JobApplication(BaseIntModel):
    """Model for tracking job applications"""
    job = models.OneToOneField('jobboards.Job', on_delete=models.CASCADE, related_name='application')
    date_applied = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=50, choices=JobStatus.CHOICES, default=JobStatus.APPLIED)
    resume_version = models.CharField(max_length=255, blank=True, 
                                   help_text="Reference to which resume version was used")
    cover_letter_version = models.CharField(max_length=255, blank=True,
                                         help_text="Reference to which cover letter was used")
    notes = models.TextField(blank=True)
    # Add related_name to avoid clashes
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='jobboard_applications')
    
    class Meta:
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['date_applied']),
        ]



class FeedSource(BaseIntModel):
    """Feed source configuration."""
    
    name = models.CharField(max_length=100, unique=True)
    url = models.URLField(max_length=500)
    source_type = models.CharField(
        max_length=50,
        choices=[
            ('rss', 'RSS/Atom Feed'),
            ('hackernews', 'Hacker News Who Is Hiring'),
            ('reddit', 'Reddit'),
            ('custom', 'Custom Source'),
        ],
        default='rss'
    )
    is_active = models.BooleanField(default=True)
    last_fetched = models.DateTimeField(null=True, blank=True)
    fetch_interval_minutes = models.IntegerField(default=60)  # How often to fetch
    config = models.JSONField(default=dict, blank=True)  # Additional config params
    
    class Meta:
        app_label = 'jobboards'
        verbose_name = _('Feed Source')
        verbose_name_plural = _('Feed Sources')
    
    def __str__(self):
        return f"{self.name} ({self.get_source_type_display()})"


class FeedItem(BaseIntModel):
    """Represents a job posting from a feed."""
    
    title = models.CharField(max_length=255)
    description = models.TextField()
    url = models.URLField(max_length=500)
    company_name = models.CharField(max_length=255, null=True, blank=True)
    location = models.CharField(max_length=255, null=True, blank=True)
    posted_date = models.DateTimeField(null=True, blank=True)
    
    # Feed source relations
    source = models.ForeignKey(
        FeedSource, 
        related_name='items',
        on_delete=models.CASCADE
    )
    
    # Reference to original item
    guid = models.CharField(max_length=255)  # Unique ID from source
    raw_data = models.JSONField(default=dict, blank=True)  # Original data
    
    # Company profile relation (if matched)
    company_profile = models.ForeignKey(
        'companies.CompanyProfile',
        on_delete=models.SET_NULL,
        related_name='feed_items',
        null=True,
        blank=True
    )
    
    # Job analysis
    technologies = models.ManyToManyField(
        'companies.Technology',
        related_name='mentioned_in_feed_items',
        blank=True
    )
    
    # Processing status
    is_processed = models.BooleanField(default=False)
    is_relevant = models.BooleanField(default=True)  # Mark as False if not relevant
    
    # Potential job relation
    job = models.ForeignKey(
        'jobboards.Job',
        on_delete=models.SET_NULL,
        related_name='feed_sources',
        null=True,
        blank=True
    )
    
    class Meta:
        app_label = 'jobboards'
        verbose_name = _('Feed Item')
        verbose_name_plural = _('Feed Items')
        unique_together = ('source', 'guid')  # Ensure no duplicates
        indexes = [
            models.Index(fields=['posted_date']),
            models.Index(fields=['is_processed']),
            models.Index(fields=['is_relevant']),
        ]
    
    def __str__(self):
        return f"{self.title} ({self.source.name})"
    
    def link_or_create_company_profile(self):
        """Link to existing company profile or create new one."""
        if self.company_profile:
            return self.company_profile
            
        if not self.company_name:
            return None
            
        # Try to find existing company by name
        company = CompanyProfile.objects.filter(
            models.Q(name__iexact=self.company_name) | 
            models.Q(name__icontains=self.company_name)
        ).first()
        
        if not company:
            # Create new company profile
            company = CompanyProfile.objects.create(
                name=self.company_name,
                status='researching'
            )
            
        self.company_profile = company
        self.save(update_fields=['company_profile'])
        return company
    
    def extract_technologies(self, tech_list=None):
        """Extract technologies mentioned in the job description."""
        if tech_list is None:
            # Get all technologies from database
            tech_list = Technology.objects.all()
            
        found_techs = []
        for tech in tech_list:
            # Simple keyword matching - could be improved with NLP
            if tech.name.lower() in self.description.lower() or tech.name.lower() in self.title.lower():
                found_techs.append(tech)
                
        # Add found technologies
        self.technologies.add(*found_techs)
        return found_techs


class FeedFetchLog(BaseIntModel):
    """Log of feed fetch operations."""
    
    source = models.ForeignKey(
        FeedSource, 
        related_name='fetch_logs',
        on_delete=models.CASCADE
    )
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    success = models.BooleanField(default=False)
    items_fetched = models.IntegerField(default=0)
    items_new = models.IntegerField(default=0)  # New items added
    error_message = models.TextField(blank=True)
    
    class Meta:
        app_label = 'jobboards'
        verbose_name = _('Feed Fetch Log')
        verbose_name_plural = _('Feed Fetch Logs')
        
    def __str__(self):
        status = "Success" if self.success else "Failed"
        return f"{self.source.name} fetch on {self.start_time} - {status}"
    
