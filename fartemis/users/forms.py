from allauth.account.forms import SignupForm
from allauth.socialaccount.forms import SignupForm as SocialSignupForm
from django.contrib.auth import forms as admin_forms
from django.forms import EmailField
from django import forms
from django.utils.translation import gettext_lazy as _
from django_recaptcha.fields import ReCaptchaField

from .models import User


class UserAdminChangeForm(admin_forms.UserChangeForm):
    class Meta(admin_forms.UserChangeForm.Meta):  # type: ignore[name-defined]
        model = User
        field_classes = {"email": EmailField}


class UserAdminCreationForm(admin_forms.UserCreationForm):
    """
    Form for User Creation in the Admin Area.
    To change user signup, see UserSignupForm and UserSocialSignupForm.
    """

    class Meta(admin_forms.UserCreationForm.Meta):  # type: ignore[name-defined]
        model = User
        fields = ("email",)
        field_classes = {"email": EmailField}
        error_messages = {
            "email": {"unique": _("This email has already been taken.")},
        }


class UserSignupForm(SignupForm):
    """
    Form that will be rendered on a user sign up section/screen.
    Default fields will be added automatically.
    Check UserSocialSignupForm for accounts created from social.
    """


class UserSocialSignupForm(SocialSignupForm):
    """
    Renders the form when user has signed up using social accounts.
    Default fields will be added automatically.
    See UserSignupForm otherwise.
    """

# landing page contact form 
PROJECT_TYPE_CHOICES = [
    ('', 'Select project type'), # Placeholder
    ('healthcare', 'Healthcare Data'),
    ('blockchain', 'Blockchain/Crypto'),
    ('fintech', 'Fintech Compliance'),
    ('mobile', 'Mobile Development'),
    ('ai', 'AI/LLM Integration'),
    ('other', 'Other'),
]

class ContactForm(forms.Form):
    first_name = forms.CharField(max_length=100, label='First name',
                                widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'John'}))
    last_name = forms.CharField(max_length=100, label='Last name',
                                widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Doe'}))
    email = forms.EmailField(label='Email',
                            widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'john.doe@example.com'}))
    company = forms.CharField(max_length=100, required=False, label='Company',
                            widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your company'}))
    project_type = forms.ChoiceField(choices=PROJECT_TYPE_CHOICES, label='Project Type',
                                    widget=forms.Select(attrs={'class': 'form-select'}))
    message = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Tell us about your project and specific needs...'}),
                            label='Project Details')
    captcha = ReCaptchaField()


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make the empty value for project_type disabled
        self.fields['project_type'].choices[0] = ('', 'Select project type')
        self.fields['project_type'].widget.attrs.update({'onchange': 'this.options[0].disabled = true;'})