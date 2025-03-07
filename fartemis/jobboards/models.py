"""

"""
from django.db import models
from django.utils import timezone
from django.conf import settings

from fartemis.inherits.models import BaseIntModel
from fartemis.jobboards.constants import JobSource, JobStatus, JobLevel, EmploymentType


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

