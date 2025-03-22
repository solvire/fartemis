from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import FeedSource, FeedItem, Job


@admin.register(FeedSource)
class FeedSourceAdmin(admin.ModelAdmin):
    """Admin interface for feed sources."""
    list_display = ('name', 'source_type', 'url', 'is_active', 'last_fetched')
    list_filter = ('source_type', 'is_active')
    search_fields = ('name', 'url')
    readonly_fields = ('last_fetched',)
    fieldsets = (
        (None, {
            'fields': ('name', 'url', 'source_type', 'is_active')
        }),
        (_('Fetch Configuration'), {
            'fields': ('fetch_interval_minutes', 'last_fetched'),
            'classes': ('collapse',),
        }),
        (_('Advanced Configuration'), {
            'fields': ('config',),
            'classes': ('collapse',),
            'description': _('Additional configuration in JSON format')
        }),
    )
    actions = ['mark_active', 'mark_inactive']

    def mark_active(self, request, queryset):
        """Mark selected feed sources as active."""
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} feed sources marked as active.")
    mark_active.short_description = _("Mark selected feed sources as active")

    def mark_inactive(self, request, queryset):
        """Mark selected feed sources as inactive."""
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} feed sources marked as inactive.")
    mark_inactive.short_description = _("Mark selected feed sources as inactive")


@admin.register(FeedItem)
class FeedItemAdmin(admin.ModelAdmin):
    """Admin interface for feed items."""
    list_display = ('get_title', 'source', 'created', 'is_processed', 'has_job')
    list_filter = ('source', 'is_processed', 'created')
    search_fields = ('guid', 'raw_data')
    readonly_fields = ('created', 'updated', 'guid', 'source', 'raw_data', 'job')
    fields = ('guid', 'source', 'is_processed', 'job', 'raw_data', 'created', 'updated')
    actions = ['mark_processed', 'mark_unprocessed']

    def get_title(self, obj):
        """Get the title from raw_data if available."""
        if isinstance(obj.raw_data, dict) and 'title' in obj.raw_data:
            return obj.raw_data['title']
        return obj.guid
    get_title.short_description = _('Title')
    
    def has_job(self, obj):
        """Check if the feed item has a linked job."""
        return bool(obj.job)
    has_job.boolean = True
    has_job.short_description = _('Has Job')

    def mark_processed(self, request, queryset):
        """Mark selected feed items as processed."""
        updated = queryset.update(is_processed=True)
        self.message_user(request, f"{updated} feed items marked as processed.")
    mark_processed.short_description = _("Mark selected feed items as processed")

    def mark_unprocessed(self, request, queryset):
        """Mark selected feed items as unprocessed."""
        updated = queryset.update(is_processed=False)
        self.message_user(request, f"{updated} feed items marked as unprocessed.")
    mark_unprocessed.short_description = _("Mark selected feed items as unprocessed")
    
    def has_add_permission(self, request):
        """Disable adding feed items through admin."""
        return False


# Register Job model if not already registered
if not admin.site.is_registered(Job):
    @admin.register(Job)
    class JobAdmin(admin.ModelAdmin):
        """Admin interface for jobs."""
        list_display = ('title', 'company_name', 'location', 'remote', 'source', 'posted_date', 'status')
        list_filter = ('source', 'remote', 'status', 'employment_type', 'job_level', 'posted_date')
        search_fields = ('title', 'company_name', 'description', 'location')
        readonly_fields = ('created', 'updated')
        fieldsets = (
            (None, {
                'fields': ('title', 'company_name', 'company_profile', 'location', 'remote', 'url')
            }),
            (_('Job Details'), {
                'fields': ('description', 'description_html', 'employment_type', 'job_level', 'required_skills', 'keywords')
            }),
            (_('Source Information'), {
                'fields': ('source', 'source_id', 'posted_date', 'expires_date')
            }),
            (_('Salary Information'), {
                'fields': ('salary_min', 'salary_max', 'salary_currency'),
                'classes': ('collapse',),
            }),
            (_('Status and Relevance'), {
                'fields': ('status', 'relevance_score')
            }),
            (_('System Information'), {
                'fields': ('created', 'updated'),
                'classes': ('collapse',),
            }),
        )
        filter_horizontal = ('search_queries',)
        actions = ['mark_active', 'mark_expired', 'recalculate_relevance']
        
        def mark_active(self, request, queryset):
            """Mark selected jobs as active."""
            updated = queryset.update(status='active')
            self.message_user(request, f"{updated} jobs marked as active.")
        mark_active.short_description = _("Mark selected jobs as active")
        
        def mark_expired(self, request, queryset):
            """Mark selected jobs as expired."""
            updated = queryset.update(status='expired')
            self.message_user(request, f"{updated} jobs marked as expired.")
        mark_expired.short_description = _("Mark selected jobs as expired")
        
        def recalculate_relevance(self, request, queryset):
            """Recalculate relevance score for selected jobs."""
            for job in queryset:
                # This would typically call your relevance calculation method
                # For now, we'll just add a placeholder
                self.message_user(request, f"Relevance recalculation not implemented yet.")
                break
        recalculate_relevance.short_description = _("Recalculate relevance scores")