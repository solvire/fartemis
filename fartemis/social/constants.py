from django.utils.translation import gettext_lazy as _



class Social:
    BLUESKY = 'bluesky'
    X = 'x'
    LINKEDIN = 'linkedin'
    META = 'meta'
    SUBSTACK = 'substack'
    GITHUB = 'github'
    MEDIUM = 'medium'
    
    PLATFORM_CHOICES = [
        (BLUESKY, _('Bluesky')),
        (X, _('X/Twitter')),
        (LINKEDIN, _('LinkedIn')),
        (META, _('Meta/Facebook')),
        (SUBSTACK, _('Substack')),
        (GITHUB, _('GitHub')),
        (MEDIUM, _('Medium')),
    ]

class ContentType:
    COMMIT_SUMMARY = 'commit_summary'
    MILESTONE = 'milestone'
    ANNOUNCEMENT = 'announcement'
    JOB_INSIGHT = 'job_insight'
    TUTORIAL = 'tutorial'
    OTHER = 'other'
    
    CHOICES = [
        (COMMIT_SUMMARY, _('Commit Summary')),
        (MILESTONE, _('Project Milestone')),
        (ANNOUNCEMENT, _('Announcement')),
        (JOB_INSIGHT, _('Job Market Insight')),
        (TUTORIAL, _('Tutorial')),
        (OTHER, _('Other')),
    ]

class ContentStatus:
    DRAFT = 'draft'
    READY = 'ready'
    PUBLISHED = 'published'
    FAILED = 'failed'
    ARCHIVED = 'archived'
    
    CHOICES = [
        (DRAFT, _('Draft')),
        (READY, _('Ready to Publish')),
        (PUBLISHED, _('Published')),
        (FAILED, _('Failed to Publish')),
        (ARCHIVED, _('Archived')),
    ]

class PublicationStatus:
    PENDING = 'pending'
    PUBLISHED = 'published'
    FAILED = 'failed'
    DELETED = 'deleted'
    
    CHOICES = [
        (PENDING, _('Pending')),
        (PUBLISHED, _('Published')),
        (FAILED, _('Failed')),
        (DELETED, _('Deleted From Platform')),
    ]

class ContentOrigin:
    GITHUB = Social.GITHUB
    BLUESKY = Social.BLUESKY
    X = Social.X
    LINKEDIN = Social.LINKEDIN
    META = Social.META
    SUBSTACK = Social.SUBSTACK
    MEDIUM = Social.MEDIUM
    MANUAL = 'manual'
    API = 'api'
    
    CHOICES = [
        (GITHUB, _('GitHub')),
        (BLUESKY, _('Bluesky')),
        (X, _('X/Twitter')),
        (LINKEDIN, _('LinkedIn')),
        (META, _('Meta/Facebook')),
        (SUBSTACK, _('Substack')),
        (MEDIUM, _('Medium')),
        (MANUAL, _('Manually Created')),
        (API, _('External API')),
    ]

