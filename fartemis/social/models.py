from django.conf import settings
from django.db import models

from fartemis.inherits.models import BaseIntModel

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
        'companies.CompanyProfile',
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
        'companies.CompanyProfile',
        on_delete=models.CASCADE,
        related_name='social_posts'
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