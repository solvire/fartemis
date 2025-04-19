
from typing import ClassVar
import uuid
from django.contrib.auth.models import AbstractUser
from django.db.models import CharField, UUIDField, EmailField, JSONField
from django.db import models
from django.conf import settings

from django.urls import reverse
from django.utils.translation import gettext_lazy as _


from fartemis.inherits.models import BaseIntModel

from .managers import UserManager



class User(AbstractUser):
    """
    Default custom user model for fartemis.
    If adding fields that need to be filled at user signup,
    check forms.SignupForm and forms.SocialSignupForms accordingly.
    """

    # First and last name do not cover name patterns around the globe
    # name = CharField(_("Name of User"), blank=True, max_length=255)

    id = UUIDField(primary_key=True, default=uuid.uuid4, editable=False)


    first_name = CharField(
        max_length=145, null=True, blank=True, verbose_name=_("First Name")
    )
    last_name = CharField(
        max_length=145, null=True, blank=True, verbose_name=_("Last Name")
    )
    middle_name = CharField(
        max_length=145, null=True, blank=True, verbose_name=_("Middle Name")
    )
    alternate_names = JSONField(
        null=True, blank=True, verbose_name=_("Alternate Names")
    )
    email = EmailField(_("email address"), unique=True)
    username = None  # type: ignore[assignment]

    # social media handles
    twitter_handle = CharField(
        max_length=145, null=True, blank=True, verbose_name=_("Twitter Handle")
    )
    linkedin_handle = CharField(
        max_length=145, null=True, blank=True, verbose_name=_("LinkedIn Handle")
    )
    github_handle = CharField(
        max_length=145, null=True, blank=True, verbose_name=_("GitHub Handle")
    )
    bluesky_handle = CharField(
        max_length=145, null=True, blank=True, verbose_name=_("Bluesky Handle")
    )
    substack_url = CharField(
        max_length=145, null=True, blank=True, verbose_name=_("Substack URL")
    )


    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects: ClassVar[UserManager] = UserManager()

    def get_absolute_url(self) -> str:
        """Get URL for user's detail view.

        Returns:
            str: URL for user detail.

        """
        return reverse("users:detail", kwargs={"pk": self.id})



class UserSourceLink(BaseIntModel):
    """Stores source links for a user"""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='source_links'
    )
    url = models.URLField()
    source_type = models.CharField(
        max_length=50,
        choices=[
            ('linkedin', 'LinkedIn'),
            ('article', 'Article'),
            ('blog', 'Blog Post'),
            ('mention', 'Mention'),
            ('other', 'Other')
        ]
    )
    title = models.CharField(max_length=255, blank=True)
    discovery_date = models.DateTimeField(auto_now_add=True)
    relevance_score = models.FloatField(default=0.5)
    notes = models.TextField(blank=True)
    
    class Meta:
        unique_together = ('user', 'url')
        
    def __str__(self):
        return f"{self.user} - {self.source_type}: {self.title}"


# store additional emails
class UserAdditionalEmail(BaseIntModel):
    """
    Stores additional emails for a user
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='additional_emails'
    )
    email = models.EmailField()
    is_primary = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ('user', 'email')
        
    def __str__(self):
        return f"{self.user} - {self.email}"


# store phone numbers
class UserPhoneNumber(BaseIntModel):
    """
    Stores phone numbers for a user
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='phone_numbers'
    )
    phone_number = models.CharField(max_length=20)
    is_primary = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ('user', 'phone_number')
        
    def __str__(self):
        return f"{self.user} - {self.phone_number}"


class ContactMethodType(BaseIntModel):
    """
    Defines types of contact methods (e.g., Work Email, Personal Email, Mobile Phone)
    """
    name = models.CharField(max_length=100, unique=True)
    category = models.CharField(
        max_length=20,
        choices=[
            ('email', 'Email'),
            ('phone', 'Phone'),
            ('messaging', 'Messaging App'),
            ('other', 'Other')
        ]
    )
    
    def __str__(self):
        return self.name

class UserContactMethod(BaseIntModel):
    """
    Stores multiple contact methods per user
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        related_name='contact_methods'
    )
    method_type = models.ForeignKey(
        ContactMethodType,
        on_delete=models.PROTECT,
        related_name='user_methods'
    )
    value = models.CharField(max_length=255)  # The actual email, phone number, etc.
    is_primary = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ('user', 'method_type', 'value')
        
    def __str__(self):
        return f"{self.user} - {self.method_type}: {self.value}"
    
    def save(self, *args, **kwargs):
        # Ensure only one primary contact method per user per type
        if self.is_primary:
            UserContactMethod.objects.filter(
                user=self.user,
                method_type__category=self.method_type.category,
                is_primary=True
            ).update(is_primary=False)
        super().save(*args, **kwargs)