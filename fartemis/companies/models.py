"""
Models for job listings, job applications, and job search queries
@author: solvire
@date: 2025-03-03
"""
from django.db import models
from django.utils import timezone
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator

from fartemis.inherits.models import BaseIntModel
from fartemis.jobboards.constants import JobSource, JobStatus, JobLevel, EmploymentType

from . import constants



class CompanyProfile(BaseIntModel):
    """
    Represents a company that could be a potential employer or target for applications.
    Stores core information about the company separate from any specific job listings.
    """
    name = models.CharField(max_length=255, verbose_name="Company Name")
    website = models.URLField(blank=True, null=True)
    careers_page_url = models.URLField(blank=True, null=True)
    open_jobs_count = models.PositiveIntegerField(default=0)
    description = models.TextField(blank=True, null=True)
    linkedin_id = models.CharField(max_length=255, blank=True)
    
    # Company size and details
    founded_year = models.PositiveIntegerField(blank=True, null=True)
    employee_count_min = models.PositiveIntegerField(blank=True, null=True) 
    employee_count_max = models.PositiveIntegerField(blank=True, null=True)
    
    # Location information
    headquarters_city = models.CharField(max_length=100, blank=True, null=True)
    headquarters_state = models.CharField(max_length=100, blank=True, null=True)
    headquarters_country = models.CharField(max_length=100, blank=True, null=True)
    
    # Business classification
    is_public = models.BooleanField(default=False)
    stock_symbol = models.CharField(max_length=10, blank=True, null=True)
    
    # AI-generated analysis and notes
    ai_analysis = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    funding_status = models.CharField(max_length=100, choices=constants.FundingStatus.CHOICES, blank=True)
    funding_rounds = models.JSONField(default=list, blank=True)
    latest_funding_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    latest_funding_date = models.DateField(null=True, blank=True)
    total_funding = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    # Sentiment data
    glassdoor_rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    indeed_rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    employee_sentiment_score = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)

    # Technical reputation
    github_repos = models.IntegerField(null=True, blank=True)
    github_stars = models.IntegerField(null=True, blank=True)
    open_source_contribution_score = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    
    # Continuous monitoring fields
    last_sentiment_update = models.DateTimeField(null=True, blank=True)
    last_funding_update = models.DateTimeField(null=True, blank=True)
    
    # Media and content
    recent_news = models.JSONField(default=list, blank=True)
    social_media_handles = models.JSONField(default=dict, blank=True)
    sentiment_data_points = models.JSONField(default=dict, blank=True)
    
    class Meta:
        # app_label = 'fartemis.companies'
        verbose_name = "Company Profile"
        verbose_name_plural = "Company Profiles"
        
    def __str__(self):
        return self.name
        
    @property
    def employee_size_display(self):
        """Display employee size as a range or single value when only one is provided"""
        if self.employee_count_min and self.employee_count_max:
            return f"{self.employee_count_min:,} - {self.employee_count_max:,}"
        elif self.employee_count_min:
            return f"{self.employee_count_min:,}+"
        elif self.employee_count_max:
            return f"Up to {self.employee_count_max:,}"
        return "Unknown"
    
class CompanyResearchReferences(BaseIntModel):
    """
    Links to external sources for company research
    """
    company = models.ForeignKey(
        CompanyProfile,
        on_delete=models.CASCADE,
        related_name='research_references'
    )
    title = models.CharField(max_length=255)
    url = models.URLField()
    content = models.TextField(blank=True, null=True)
    sentiment = models.CharField(max_length=100, choices=constants.CompanyReviewSentiment.CHOICES, blank=True)
    
    class Meta:
        verbose_name = "Company Research Reference"
        verbose_name_plural = "Company Research References"
    
    def __str__(self):
        return self.title + " - " + self.sentiment
    
class CompanyResearchLog(BaseIntModel):
    """
    Log of research activities and results of AI content generation for a company
    """
    company = models.ForeignKey(
        CompanyProfile,
        on_delete=models.CASCADE,
        related_name='research_logs'
    )

    content = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Company Research Log"
        verbose_name_plural = "Company Research Logs"
    
    def __str__(self):
        return f"{self.company}"


class CompanyRole(BaseIntModel):
    """
    Defines roles a person can have at a company (e.g., Recruiter, Hiring Manager)
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return self.name


class UserCompanyAssociation(BaseIntModel):
    """
    Links users to companies with their roles and job titles
    One person can have multiple roles across different companies
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='company_associations'
    )
    company = models.ForeignKey(
        CompanyProfile,
        on_delete=models.CASCADE,
        related_name='personnel'
    )
    job_title = models.CharField(max_length=255, blank=True, null=True)
    department = models.CharField(max_length=255, blank=True, null=True)
    role = models.ForeignKey(
        CompanyRole,
        on_delete=models.PROTECT,
        related_name='user_associations',
        null=True,
        blank=True
    )
    
    # For networking prioritization
    influence_level = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Scale of 1-10 indicating this person's influence in hiring decisions"
    )
    
    # Relationship tracking
    STATUS_CHOICES = [
        ('to_contact', 'To Contact'),
        ('contacted', 'Contacted'),
        ('responded', 'Responded'),
        ('meeting_scheduled', 'Meeting Scheduled'),
        ('connected', 'Connected'),
        ('not_responsive', 'Not Responsive')
    ]
    relationship_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='to_contact'
    )
    
    # Additional metadata
    notes = models.TextField(blank=True, null=True)
    last_contact_date = models.DateTimeField(blank=True, null=True)
    next_contact_date = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        unique_together = ('user', 'company', 'job_title')
        verbose_name = "Company Association"
        verbose_name_plural = "Company Associations"
        
    def __str__(self):
        return f"{self.user} at {self.company} - {self.job_title or 'No title'}"


class Industry(BaseIntModel):
    """
    Industries that companies operate in
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    is_target = models.BooleanField(default=False, 
                                  help_text="Mark industries you're targeting in your job search")
    
    class Meta:
        verbose_name_plural = "Industries"
    
    def __str__(self):
        return self.name


class CompanyIndustry(BaseIntModel):
    """
    Many-to-many relationship between companies and industries
    """
    company = models.ForeignKey(
        CompanyProfile,
        on_delete=models.CASCADE,
        related_name='industry_associations'
    )
    industry = models.ForeignKey(
        Industry,
        on_delete=models.CASCADE,
        related_name='companies'
    )
    is_primary = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ('company', 'industry')
        verbose_name_plural = "Company Industries"
    
    def __str__(self):
        return f"{self.company} - {self.industry}"
    
    def save(self, *args, **kwargs):
        # Ensure only one primary industry per company
        if self.is_primary:
            CompanyIndustry.objects.filter(
                company=self.company,
                is_primary=True
            ).update(is_primary=False)
        super().save(*args, **kwargs)


class Technology(BaseIntModel):
    """
    Technologies used by companies 
    """
    name = models.CharField(max_length=100, unique=True)
    category = models.CharField(max_length=100)  # e.g., "Programming Language", "Framework", "Database"
    description = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Technologies"
    
    def __str__(self):
        return self.name


class CompanyTechnology(BaseIntModel):
    """
    Many-to-many relationship between companies and technologies they use
    """
    company = models.ForeignKey(
        CompanyProfile,
        on_delete=models.CASCADE,
        related_name='technologies'
    )
    technology = models.ForeignKey(
        Technology,
        on_delete=models.CASCADE,
        related_name='companies'
    )
    
    class Meta:
        unique_together = ('company', 'technology')
        verbose_name_plural = "Company Technologies"
    
    def __str__(self):
        return f"{self.company} - {self.technology}"

