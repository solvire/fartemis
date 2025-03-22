from django.contrib import admin
from fartemis.companies.models import (
    CompanyProfile, 
    CompanyRole, 
    UserCompanyAssociation,
    Industry,
    CompanyIndustry,
    Technology,
    CompanyTechnology
)

@admin.register(CompanyProfile)
class CompanyProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'headquarters_city', 'employee_size_display')
    list_filter = ('is_public',)
    search_fields = ('name', 'description', 'headquarters_city', 'headquarters_country')
    fieldsets = (
        (None, {
            'fields': ('name', 'website', 'description')
        }),
        ('Company Details', {
            'fields': ('founded_year', 'employee_count_min', 'employee_count_max', 
                     'headquarters_city', 'headquarters_country')
        }),
        ('Business Information', {
            'fields': ('is_public', 'stock_symbol')
        }),
        ('Notes', {
            'fields': ('ai_analysis', 'notes')
        }),
    )


@admin.register(CompanyRole)
class CompanyRoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name', 'description')


class CompanyIndustryInline(admin.TabularInline):
    model = CompanyIndustry
    extra = 1


class CompanyTechnologyInline(admin.TabularInline):
    model = CompanyTechnology
    extra = 1


class UserCompanyAssociationInline(admin.TabularInline):
    model = UserCompanyAssociation
    extra = 1
    fields = ('user', 'job_title', 'role', 'influence_level', 'relationship_status')


@admin.register(UserCompanyAssociation)
class UserCompanyAssociationAdmin(admin.ModelAdmin):
    list_display = ('user', 'company', 'job_title', 'role', 'relationship_status')
    list_filter = ('relationship_status', 'role')
    search_fields = ('user__username', 'user__email', 'company__name', 'job_title')
    raw_id_fields = ('user', 'company')


@admin.register(Industry)
class IndustryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_target')
    list_filter = ('is_target',)
    search_fields = ('name', 'description')


@admin.register(Technology)
class TechnologyAdmin(admin.ModelAdmin):
    list_display = ('name', 'category')
    list_filter = ('category',)
    search_fields = ('name', 'description', 'category')