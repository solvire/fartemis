import logging
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.http import HttpResponse
from django.db.models import QuerySet
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.template.loader import render_to_string
from django.shortcuts import redirect
from django.shortcuts import render
from django.core.mail import send_mail
from django.views.generic import DetailView
from django.views.generic import RedirectView
from django.views.generic import UpdateView

from fartemis.users.models import User
from fartemis.users.forms import ContactForm

logger = logging.getLogger(__name__)


class UserDetailView(LoginRequiredMixin, DetailView):
    model = User
    slug_field = "id"
    slug_url_kwarg = "id"


user_detail_view = UserDetailView.as_view()


class UserUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = User
    fields = ["name"]
    success_message = _("Information successfully updated")

    def get_success_url(self) -> str:
        assert self.request.user.is_authenticated  # type guard
        return self.request.user.get_absolute_url()

    def get_object(self, queryset: QuerySet | None=None) -> User:
        assert self.request.user.is_authenticated  # type guard
        return self.request.user


user_update_view = UserUpdateView.as_view()


class UserRedirectView(LoginRequiredMixin, RedirectView):
    permanent = False

    def get_redirect_url(self) -> str:
        return reverse("users:detail", kwargs={"pk": self.request.user.pk})


user_redirect_view = UserRedirectView.as_view()


def home_page_view(request):
    """
    Displays the main landing page with the contact form.
    """
    contact_form = ContactForm()
    template_name = 'pages/home.html' # Your main landing page template
    context = {
        'page_title': 'DTAC - Data Solutions',
        'contact_form': contact_form,
    }
    return render(request, template_name, context)

def contact_submit_view(request):
    """
    Handles HTMX POST submission for the contact form.
    Returns a partial HTML snippet.
    """
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            # --- HONEYPOT CHECK ---
            # Access the cleaned data for your honeypot field by its name
            if form.cleaned_data.get('thepot'): # Or whatever you named it in forms.py
                # Honeypot field was filled, likely a bot.
                # You can log this attempt if you want.
                logger.info(f"Honeypot triggered by submission: {request.POST}")
                # Silently "succeed" from the bot's perspective but don't send an email.
                # This prevents the bot from knowing its strategy failed.
                context = {'form_submitted_successfully': True} # Simulates success
                return render(request, 'pages/partials/contact_form_partial.html', context)
            # --- END HONEYPOT CHECK ---
            first_name = form.cleaned_data['first_name']
            last_name = form.cleaned_data['last_name']
            email = form.cleaned_data['email']
            company = form.cleaned_data.get('company', '')
            project_type_code = form.cleaned_data['project_type']
            message_body = form.cleaned_data['message']

            # Get the display name for project_type
            project_type_display = ""
            for code, name in form.fields['project_type'].choices:
                if code == project_type_code:
                    project_type_display = name
                    break
            
            subject = f'New DTAC.io Contact: {first_name} {last_name}'
            email_context = {
                'first_name': first_name,
                'last_name': last_name,
                'email': email,
                'company': company,
                'project_type': project_type_display,
                'message_body': message_body,
            }
            
            html_message = render_to_string('emails/contact_form.html', email_context) # Ensure correct path
            plain_message = render_to_string('emails/contact_form.txt', email_context) # Ensure correct path

            try:
                send_mail(
                    subject,
                    plain_message,
                    settings.EMAIL_DEFAULT_FROM,
                    [settings.ADMINS[0][1]],  # Send to the first admin email
                    html_message=html_message,
                    fail_silently=False,
                )
                # For HTMX, return the partial with success message
                context = {'form_submitted_successfully': True}
                # It's good practice to set HX-Trigger for client-side events if needed
                # response = render(request, 'pages/partials/contact_form_partial.html', context)
                # response['HX-Trigger'] = 'contactFormSuccess' 
                # return response
                return render(request, 'pages/partials/contact_form_partial.html', context)

            except Exception as e:
                logger.info(f"Error sending email: {e}") # Log this
                # Return the form with a generic error message for HTMX
                # You can add specific non-field errors to the form if needed
                form.add_error(None, f"Sorry, there was an error sending your message. Please try again. {e}")
                context = {'form': form, 'form_submitted_successfully': False}
                return render(request, 'pages/partials/contact_form_partial.html', context)
        else:
            # Form is not valid, return the form with errors for HTMX
            context = {'form': form, 'form_submitted_successfully': False}
            return render(request, 'pages/partials/contact_form_partial.html', context)
    
    # Should not be reached via GET for this HTMX setup if form is on another page
    # Or, if this view IS also for initially loading the form via HTMX:
    # form = ContactForm()
    # context = {'form': form, 'form_submitted_successfully': False}
    # return render(request, 'pages/partials/contact_form_partial.html', context)
    return HttpResponse("Method not allowed for this HTMX endpoint.", status=405)