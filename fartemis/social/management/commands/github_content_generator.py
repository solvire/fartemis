# social/management/commands/github_content_generator.py
"""
# Preview mode (dry run with verbose output)
python manage.py github_content_generator --dry-run --verbose

# Test with a specific repository
python manage.py github_content_generator --owner=yourusername --repo=fartemis --dry-run --verbose

# Test with a specific timeframe
python manage.py github_content_generator --days=7 --dry-run --verbose

# Generate and save to database
python manage.py github_content_generator --verbose
"""

import logging
from django.core.management.base import BaseCommand
from django.conf import settings

from fartemis.social.controllers import GitHubIntegrationController
from fartemis.social.models import DocumentationEntry, PublishContent

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Generate content from GitHub commits'

    def add_arguments(self, parser):
        parser.add_argument(
            '--owner',
            type=str,
            default=settings.GITHUB_REPO_OWNER,
            help='GitHub repository owner'
        )
        parser.add_argument(
            '--repo',
            type=str,
            default=settings.GITHUB_REPO_NAME,
            help='GitHub repository name'
        )
        parser.add_argument(
            '--days',
            type=int,
            default=1,
            help='Number of days to look back for commits'
        )
        parser.add_argument(
            '--branch',
            type=str,
            help='Branch to monitor (optional)'
        )
        parser.add_argument(
            '--release-version',  # Changed from --version to --release-version
            type=str,
            help='Version to use for the changelog (e.g., 0.1.2)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Generate content but do not save to database'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output including content previews'
        )

    def handle(self, *args, **options):
        try:
            self.stdout.write(self.style.SUCCESS('Checking GitHub for commits...'))
            
            controller = GitHubIntegrationController(
                repo_owner=options['owner'],
                repo_name=options['repo'],
                version=options.get('release_version')  # Changed from 'version' to 'release_version'
            )
            
            # First fetch commits for preview
            commits = controller.fetch_recent_commits(
                days=options['days'],
                branch=options['branch']
            )
            
            if not commits:
                self.stdout.write(self.style.WARNING('No commits found in the specified timeframe'))
                return
                
            self.stdout.write(self.style.SUCCESS(f'Found {len(commits)} commits'))
            
            # Preview commits if verbose
            if options['verbose']:
                self.stdout.write('\nCommits:')
                for i, commit in enumerate(commits[:5], 1):
                    commit_message = commit.commit.message.split('\n')[0]
                    self.stdout.write(f"{i}. {commit.sha[:7]} - {commit_message}")
                
                if len(commits) > 5:
                    self.stdout.write(f"...and {len(commits) - 5} more")
            
            # Generate summary and documentation for preview
            summary = controller.generate_commit_summary(commits)
            documentation = controller.generate_documentation(commits)
            
            # Display previews if verbose
            if options['verbose'] and summary:
                self.stdout.write('\n' + '=' * 50)
                self.stdout.write('SOCIAL MEDIA CONTENT PREVIEW:')
                self.stdout.write('=' * 50)
                self.stdout.write(f"Title: {summary['title']}")
                self.stdout.write(f"Bluesky: {summary['short_content']}")
                self.stdout.write(f"Twitter: {summary['micro_content']}")
                self.stdout.write(f"Hashtags: {', '.join(summary['hashtags'])}")
                self.stdout.write(f"Body: {summary['body']}")
            
            if options['verbose'] and documentation:
                self.stdout.write('\n' + '=' * 50)
                self.stdout.write('CHANGELOG ENTRY PREVIEW:')
                self.stdout.write('=' * 50)
                self.stdout.write(documentation)
            
            # If not dry run, create content
            if not options['dry_run']:
                content = PublishContent(
                    title=summary['title'],
                    body=summary['body'],
                    short_content=summary['short_content'],
                    micro_content=summary['micro_content'],
                    content_type='commit_summary',
                    hashtags=summary['hashtags'],
                    origin_type='github',
                    origin_id=commits[0].sha,
                    status='ready'
                )
                
                content.save()
                self.stdout.write(self.style.SUCCESS(f'Created content: {content.id}'))
                
                # Save documentation if generated
                if documentation:
                    doc_entry = DocumentationEntry(
                        title=f"Changelog Entry - v{controller.version}",
                        content=documentation,
                        doc_type='changelog',
                        publish_content=content,
                        commit_sha=content.origin_id
                    )
                    doc_entry.save()
                    self.stdout.write(self.style.SUCCESS(f'Changelog entry for v{controller.version} generated and saved'))
            else:
                self.stdout.write(self.style.SUCCESS('\nDry run - no database changes made'))
                
        except Exception as e:
            logger.exception("Error in GitHub integration")
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))