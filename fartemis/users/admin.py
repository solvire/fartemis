from allauth.account.decorators import secure_admin_login
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import admin as auth_admin
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.utils.html import format_html

from .forms import UserAdminChangeForm
from .forms import UserAdminCreationForm
from .models import User
# --- Import the through model and potentially related ones ---
# Adjust path if your models are elsewhere
from fartemis.companies.models import UserCompanyAssociation, CompanyProfile, CompanyRole

if settings.DJANGO_ADMIN_FORCE_ALLAUTH:
    # Force the `admin` sign in process to go through the `django-allauth` workflow:
    # https://docs.allauth.org/en/latest/common/admin.html#admin
    admin.autodiscover()
    admin.site.login = secure_admin_login(admin.site.login)  # type: ignore[method-assign]


# --- Inline Admin for Company Associations ---
class UserCompanyAssociationInline(admin.TabularInline):
    model = UserCompanyAssociation
    # Explicitly define the foreign key to User (optional if only one FK to User)
    fk_name = 'user'
    # Fields from UserCompanyAssociation to display/edit in the inline
    fields = ('company', 'job_title', 'role', 'influence_level', 'relationship_status', 'last_contact_date')
    # Readonly fields if needed (e.g., calculated fields)
    # readonly_fields = ()
    # Autocomplete fields for better performance with many companies/roles
    # IMPORTANT: Requires CompanyProfileAdmin and CompanyRoleAdmin to be registered
    # AND have `search_fields` defined (e.g., search_fields = ['name'])
    autocomplete_fields = ['company', 'role']
    # How many extra empty forms to show
    extra = 1
    # Add verbose names if needed
    verbose_name = "Company Association"
    verbose_name_plural = "Company Associations"
    # Ordering within the inline
    ordering = ('-last_contact_date', 'company__name')


@admin.register(User)
class UserAdmin(auth_admin.UserAdmin):
    form = UserAdminChangeForm
    add_form = UserAdminCreationForm
    # Keep original fieldsets, or customize further if needed
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "middle_name", "linkedin_handle", "github_handle", "twitter_handle")}), # Added social handles
        (_("Permissions"), {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
        # Optionally add alternate_names if you want to edit it directly
        # (_("Other Info"), {"fields": ("alternate_names",)}),
    )
    # Add method to list display
    list_display = ["email", "first_name", "last_name", "display_companies", "is_superuser"]
    search_fields = ["email", "first_name", "last_name", "linkedin_handle"] # Added more search fields
    ordering = ["id"] # Consider ordering by email or name?
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),
    )

    # --- Add the Inline to the UserAdmin ---
    inlines = [UserCompanyAssociationInline]

    # --- Method for list_display ---
    @admin.display(description='Associated Companies')
    def display_companies(self, obj):
        """Displays first few associated companies as clickable links."""
        associations = obj.company_associations.select_related('company').order_by('company__name')[:3] # Limit for display
        count = obj.company_associations.count()

        if not associations:
            return "None"

        links = []
        for assoc in associations:
            company = assoc.company
            # Make company name clickable link to company admin change page
            # Assumes CompanyProfile is registered with admin and has a change view
            try:
                company_url = reverse(f'admin:{company._meta.app_label}_{company._meta.model_name}_change', args=[company.pk])
                links.append(format_html('<a href="{}">{}</a>', company_url, company.name))
            except Exception:
                links.append(company.name) # Fallback if URL reversing fails

        display_text = ", ".join(links)
        if count > 3:
            display_text += f", ... ({count} total)"

        return format_html(display_text) # Ensure HTML is rendered safely

# @admin.register(CompanyProfile)
# class CompanyProfileAdmin(admin.ModelAdmin):
#     list_display = ('name', 'website', 'headquarters_city')
#     search_fields = ('name', 'website') # Essential for autocomplete

# @admin.register(CompanyRole)
# class CompanyRoleAdmin(admin.ModelAdmin):
#     list_display = ('name',)
#     search_fields = ('name',) # Essential for autocomplete