import logging
import hashlib

from django.conf import settings
from django.db import models

from fartemis.inherits.models import BaseIntModel
from fartemis.social.constants import Social
from fartemis.companies.models import CompanyProfile

from .constants import ContentType, ContentOrigin, ContentStatus, PublicationStatus


logger = logging.getLogger(__name__)

class SocialPlatform(BaseIntModel):
    """
    Defines different social media platforms
    """
    name = models.CharField(max_length=100, unique=True)
    base_url = models.URLField(help_text="Base URL for the platform (e.g., https://linkedin.com/in/)")
    icon_class = models.CharField(max_length=50, blank=True, null=True, help_text="CSS class for platform icon")
    
    def __str__(self):
        return self.name


class UserSocialProfile(BaseIntModel):
    """
    Stores multiple social media profiles for each user
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='social_profiles'
    )
    platform = models.ForeignKey(
        SocialPlatform,
        on_delete=models.PROTECT,
        related_name='user_profiles'
    )
    username = models.CharField(max_length=255)  # The username/handle on that platform
    profile_url = models.URLField(blank=True, null=True)
    is_public = models.BooleanField(default=True)
    last_checked = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        unique_together = ('user', 'platform', 'username')
        
    def __str__(self):
        return f"{self.user} on {self.platform}: {self.username}"
    
    def save(self, *args, **kwargs):
        # Auto-generate profile URL if possible
        if not self.profile_url and self.platform.base_url and self.username:
            self.profile_url = f"{self.platform.base_url.rstrip('/')}/{self.username}"
        super().save(*args, **kwargs)


class CompanySocialProfile(BaseIntModel):
    """
    Stores social media profiles for companies
    """
    company = models.ForeignKey(
        CompanyProfile,  # Make sure companies app is in INSTALLED_APPS
        on_delete=models.CASCADE,
        related_name='social_profiles'
    )
    platform = models.ForeignKey(
        SocialPlatform,
        on_delete=models.PROTECT,
        related_name='company_profiles'
    )
    username = models.CharField(max_length=255)
    profile_url = models.URLField(blank=True, null=True)
    follower_count = models.PositiveIntegerField(blank=True, null=True)
    last_checked = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        unique_together = ('company', 'platform', 'username')
        
    def __str__(self):
        return f"{self.company} on {self.platform}: {self.username}"
    
    def save(self, *args, **kwargs):
        # Auto-generate profile URL if possible
        if not self.profile_url and self.platform.base_url and self.username:
            self.profile_url = f"{self.platform.base_url.rstrip('/')}/{self.username}"
        super().save(*args, **kwargs)


class SocialPost(BaseIntModel):
    """
    Tracks posts made by or about companies on social media
    """
    company = models.ForeignKey(
        CompanyProfile,  # Make sure companies app is in INSTALLED_APPS
        on_delete=models.CASCADE,
        related_name='social_posts',
        null=True,
        blank=True
    )
    platform = models.ForeignKey(
        SocialPlatform,
        on_delete=models.PROTECT,
        related_name='posts'
    )
    post_url = models.URLField()
    post_date = models.DateTimeField()
    content_summary = models.TextField(blank=True, null=True)
    engagement_count = models.PositiveIntegerField(blank=True, null=True, 
                                                 help_text="Total likes, shares, comments, etc.")
    is_company_post = models.BooleanField(default=True, 
                                        help_text="True if posted by company, False if about company")
    sentiment = models.FloatField(blank=True, null=True, 
                                help_text="AI-analyzed sentiment score (-1.0 to 1.0)")

    
    class Meta:
        indexes = [
            models.Index(fields=['company', 'post_date']),
        ]
    
    def __str__(self):
        return f"{self.company} post on {self.platform} at {self.post_date}"
    


class PublishContent(BaseIntModel):
    """
    Model for content that will be published to social media platforms
    Acts as a staging area before actual posting
    """
    # Core content fields
    title = models.CharField(max_length=255, blank=True)
    body = models.TextField(help_text="Full-length content for platforms like Substack/Medium")
    
    # Platform-specific content versions
    short_content = models.CharField(max_length=300, blank=True, 
                                  help_text="Content suitable for Bluesky (300 char limit)")
    micro_content = models.CharField(max_length=280, blank=True,
                                 help_text="Content suitable for X/Twitter (280 char limit)")
    
    # Classification and metadata
    content_type = models.CharField(max_length=50, choices=ContentType.CHOICES, default=ContentType.OTHER)
    hashtags = models.JSONField(default=list, blank=True, 
                              help_text="List of hashtags to include with the content")
    
    # Origin tracking
    origin_type = models.CharField(max_length=50, choices=ContentOrigin.CHOICES, blank=True, 
                                help_text="Where this content originated")
    origin_id = models.CharField(max_length=255, blank=True,
                              help_text="Identifier for the origin (commit SHA, etc.)")
    
    # Publishing state
    status = models.CharField(max_length=20, choices=ContentStatus.CHOICES, default=ContentStatus.DRAFT)
    
    # Author information
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Duplication prevention
    content_hash = models.CharField(max_length=64, blank=True, unique=True,
                                 help_text="Hash to prevent duplicate content")
    
    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['content_type']),
            models.Index(fields=['origin_type', 'origin_id']),
        ]
        ordering = ['-created']
    
    def __str__(self):
        return self.title if self.title else f"{self.content_type} - {self.id}"
    
    def save(self, *args, **kwargs):
        # Generate hash if not provided
        if not self.content_hash:
            # Create hash from the core content fields to detect duplicates
            content_to_hash = f"{self.title}|{self.body}|{self.short_content}|{self.micro_content}|{self.origin_type}|{self.origin_id}"
            self.content_hash = hashlib.sha256(content_to_hash.encode('utf-8')).hexdigest()
        super().save(*args, **kwargs)


class CommunicationLog(BaseIntModel):
    """
    Logs when content is published to external platforms
    Stores the actual content published and tracks engagement metrics
    """
    # Reference to the source content (optional)
    source_content = models.ForeignKey(
        'PublishContent', 
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='publications',
        help_text="Reference to the original content, if available"
    )
    
    # The actual content that was published
    content_title = models.CharField(max_length=255, blank=True)
    content_body = models.TextField(blank=True, help_text="The actual content that was published")
    content_type = models.CharField(max_length=50, choices=ContentType.CHOICES, default=ContentType.OTHER)
    hashtags = models.JSONField(default=list, blank=True)
    
    # Publication details
    platform = models.CharField(max_length=50, choices=Social.PLATFORM_CHOICES)
    status = models.CharField(max_length=20, choices=PublicationStatus.CHOICES, default=PublicationStatus.PENDING)
    published_at = models.DateTimeField(null=True, blank=True)
    
    # Platform-specific identifiers
    external_id = models.CharField(
        max_length=255, 
        blank=True, 
        help_text="ID of the post on the platform"
    )
    external_url = models.URLField(
        blank=True, 
        help_text="URL to the published content"
    )
    
    # Error tracking
    error_message = models.TextField(blank=True)
    
    # Engagement metrics
    engagement_metrics = models.JSONField(
        default=dict, 
        blank=True, 
        help_text="Platform-specific metrics (likes, shares, etc.)"
    )
    metrics_updated_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['platform', 'published_at']),
            models.Index(fields=['status']),
            models.Index(fields=['external_id']),
            models.Index(fields=['source_content']),
        ]
        ordering = ['-created']
    
    def __str__(self):
        return f"{self.platform} post: {self.content_title or self.id}"
    

class DocumentationEntry(BaseIntModel):
    """
    Stores documentation generated from code changes
    Can be used to update README or other documentation files
    """
    TYPES = [
        ('changelog', 'Changelog Entry'),
        ('commit_summary', 'Commit Summary'),
        ('feature_docs', 'Feature Documentation'),
        ('release_notes', 'Release Notes'),
        ('api_docs', 'API Documentation'),
        ('other', 'Other')
    ]
    
    title = models.CharField(max_length=255)
    content = models.TextField(help_text="Markdown content")
    doc_type = models.CharField(max_length=50, choices=TYPES, default='commit_summary')
    
    # Link to related content if available
    publish_content = models.ForeignKey(
        PublishContent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='documentation_entries'
    )
    
    # GitHub reference
    commit_sha = models.CharField(max_length=40, blank=True)
    applied_to_repo = models.BooleanField(default=False, help_text="Whether this has been applied to the repo")
    
    class Meta:
        ordering = ['-created']
        
    def __str__(self):
        return self.title