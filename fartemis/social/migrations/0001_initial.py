# Generated by Django 5.0.12 on 2025-03-02 22:14

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("companies", "__first__"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SocialPlatform",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("updated", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=100, unique=True)),
                (
                    "base_url",
                    models.URLField(
                        help_text="Base URL for the platform (e.g., https://linkedin.com/in/)"
                    ),
                ),
                (
                    "icon_class",
                    models.CharField(
                        blank=True,
                        help_text="CSS class for platform icon",
                        max_length=50,
                        null=True,
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="PublishContent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("updated", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(blank=True, max_length=255)),
                (
                    "body",
                    models.TextField(
                        help_text="Full-length content for platforms like Substack/Medium"
                    ),
                ),
                (
                    "short_content",
                    models.CharField(
                        blank=True,
                        help_text="Content suitable for Bluesky (300 char limit)",
                        max_length=300,
                    ),
                ),
                (
                    "micro_content",
                    models.CharField(
                        blank=True,
                        help_text="Content suitable for X/Twitter (280 char limit)",
                        max_length=280,
                    ),
                ),
                (
                    "content_type",
                    models.CharField(
                        choices=[
                            ("commit_summary", "Commit Summary"),
                            ("milestone", "Project Milestone"),
                            ("announcement", "Announcement"),
                            ("job_insight", "Job Market Insight"),
                            ("tutorial", "Tutorial"),
                            ("other", "Other"),
                        ],
                        default="other",
                        max_length=50,
                    ),
                ),
                (
                    "hashtags",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="List of hashtags to include with the content",
                    ),
                ),
                (
                    "origin_type",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("github", "GitHub"),
                            ("bluesky", "Bluesky"),
                            ("x", "X/Twitter"),
                            ("linkedin", "LinkedIn"),
                            ("meta", "Meta/Facebook"),
                            ("substack", "Substack"),
                            ("medium", "Medium"),
                            ("manual", "Manually Created"),
                            ("api", "External API"),
                        ],
                        help_text="Where this content originated",
                        max_length=50,
                    ),
                ),
                (
                    "origin_id",
                    models.CharField(
                        blank=True,
                        help_text="Identifier for the origin (commit SHA, etc.)",
                        max_length=255,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("ready", "Ready to Publish"),
                            ("published", "Published"),
                            ("failed", "Failed to Publish"),
                            ("archived", "Archived"),
                        ],
                        default="draft",
                        max_length=20,
                    ),
                ),
                (
                    "content_hash",
                    models.CharField(
                        blank=True,
                        help_text="Hash to prevent duplicate content",
                        max_length=64,
                        unique=True,
                    ),
                ),
                (
                    "author",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created"],
            },
        ),
        migrations.CreateModel(
            name="DocumentationEntry",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("updated", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=255)),
                ("content", models.TextField(help_text="Markdown content")),
                (
                    "doc_type",
                    models.CharField(
                        choices=[
                            ("changelog", "Changelog Entry"),
                            ("commit_summary", "Commit Summary"),
                            ("feature_docs", "Feature Documentation"),
                            ("release_notes", "Release Notes"),
                            ("api_docs", "API Documentation"),
                            ("other", "Other"),
                        ],
                        default="commit_summary",
                        max_length=50,
                    ),
                ),
                ("commit_sha", models.CharField(blank=True, max_length=40)),
                (
                    "applied_to_repo",
                    models.BooleanField(
                        default=False,
                        help_text="Whether this has been applied to the repo",
                    ),
                ),
                (
                    "publish_content",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="documentation_entries",
                        to="social.publishcontent",
                    ),
                ),
            ],
            options={
                "ordering": ["-created"],
            },
        ),
        migrations.CreateModel(
            name="CommunicationLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("updated", models.DateTimeField(auto_now=True)),
                ("content_title", models.CharField(blank=True, max_length=255)),
                (
                    "content_body",
                    models.TextField(
                        blank=True, help_text="The actual content that was published"
                    ),
                ),
                (
                    "content_type",
                    models.CharField(
                        choices=[
                            ("commit_summary", "Commit Summary"),
                            ("milestone", "Project Milestone"),
                            ("announcement", "Announcement"),
                            ("job_insight", "Job Market Insight"),
                            ("tutorial", "Tutorial"),
                            ("other", "Other"),
                        ],
                        default="other",
                        max_length=50,
                    ),
                ),
                ("hashtags", models.JSONField(blank=True, default=list)),
                (
                    "platform",
                    models.CharField(
                        choices=[
                            ("bluesky", "Bluesky"),
                            ("x", "X/Twitter"),
                            ("linkedin", "LinkedIn"),
                            ("meta", "Meta/Facebook"),
                            ("substack", "Substack"),
                            ("github", "GitHub"),
                            ("medium", "Medium"),
                        ],
                        max_length=50,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("published", "Published"),
                            ("failed", "Failed"),
                            ("deleted", "Deleted From Platform"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                (
                    "external_id",
                    models.CharField(
                        blank=True,
                        help_text="ID of the post on the platform",
                        max_length=255,
                    ),
                ),
                (
                    "external_url",
                    models.URLField(
                        blank=True, help_text="URL to the published content"
                    ),
                ),
                ("error_message", models.TextField(blank=True)),
                (
                    "engagement_metrics",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Platform-specific metrics (likes, shares, etc.)",
                    ),
                ),
                ("metrics_updated_at", models.DateTimeField(blank=True, null=True)),
                (
                    "source_content",
                    models.ForeignKey(
                        blank=True,
                        help_text="Reference to the original content, if available",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="publications",
                        to="social.publishcontent",
                    ),
                ),
            ],
            options={
                "ordering": ["-created"],
            },
        ),
        migrations.CreateModel(
            name="CompanySocialProfile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("updated", models.DateTimeField(auto_now=True)),
                ("username", models.CharField(max_length=255)),
                ("profile_url", models.URLField(blank=True, null=True)),
                ("follower_count", models.PositiveIntegerField(blank=True, null=True)),
                ("last_checked", models.DateTimeField(blank=True, null=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="social_profiles",
                        to="companies.companyprofile",
                    ),
                ),
                (
                    "platform",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="company_profiles",
                        to="social.socialplatform",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="SocialPost",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("updated", models.DateTimeField(auto_now=True)),
                ("post_url", models.URLField()),
                ("post_date", models.DateTimeField()),
                ("content_summary", models.TextField(blank=True, null=True)),
                (
                    "engagement_count",
                    models.PositiveIntegerField(
                        blank=True,
                        help_text="Total likes, shares, comments, etc.",
                        null=True,
                    ),
                ),
                (
                    "is_company_post",
                    models.BooleanField(
                        default=True,
                        help_text="True if posted by company, False if about company",
                    ),
                ),
                (
                    "sentiment",
                    models.FloatField(
                        blank=True,
                        help_text="AI-analyzed sentiment score (-1.0 to 1.0)",
                        null=True,
                    ),
                ),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="social_posts",
                        to="companies.companyprofile",
                    ),
                ),
                (
                    "platform",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="posts",
                        to="social.socialplatform",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="UserSocialProfile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("updated", models.DateTimeField(auto_now=True)),
                ("username", models.CharField(max_length=255)),
                ("profile_url", models.URLField(blank=True, null=True)),
                ("is_public", models.BooleanField(default=True)),
                ("last_checked", models.DateTimeField(blank=True, null=True)),
                (
                    "platform",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="user_profiles",
                        to="social.socialplatform",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="social_profiles",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="publishcontent",
            index=models.Index(fields=["status"], name="social_publ_status_9bf7fa_idx"),
        ),
        migrations.AddIndex(
            model_name="publishcontent",
            index=models.Index(
                fields=["content_type"], name="social_publ_content_e2e945_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="publishcontent",
            index=models.Index(
                fields=["origin_type", "origin_id"],
                name="social_publ_origin__95b969_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="communicationlog",
            index=models.Index(
                fields=["platform", "published_at"],
                name="social_comm_platfor_6b617f_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="communicationlog",
            index=models.Index(fields=["status"], name="social_comm_status_97b81d_idx"),
        ),
        migrations.AddIndex(
            model_name="communicationlog",
            index=models.Index(
                fields=["external_id"], name="social_comm_externa_8f37da_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="communicationlog",
            index=models.Index(
                fields=["source_content"], name="social_comm_source__fa5524_idx"
            ),
        ),
        migrations.AlterUniqueTogether(
            name="companysocialprofile",
            unique_together={("company", "platform", "username")},
        ),
        migrations.AddIndex(
            model_name="socialpost",
            index=models.Index(
                fields=["company", "post_date"], name="social_soci_company_5f67b9_idx"
            ),
        ),
        migrations.AlterUniqueTogether(
            name="usersocialprofile",
            unique_together={("user", "platform", "username")},
        ),
    ]
