"""
file: fartemis/social/controllers.py

Controllers for handling social media integrations

@author: solvire
@date: 2025-03-02
"""
import logging
from datetime import datetime, timedelta
import json
from django.conf import settings

from fartemis.social.constants import Social, ContentType, ContentStatus, ContentOrigin
from fartemis.social.models import PublishContent
from fartemis.social.clients import APIClientFactory

logger = logging.getLogger(__name__)




class GitHubIntegrationController:
    """
    Controller for integrating with GitHub
    Monitors commits, generates content, and creates documentation
    """
    
    def __init__(self, repo_owner=None, repo_name=None, version=None):
        """Initialize with repository information"""
        self.github_client = APIClientFactory.generate(Social.GITHUB)
        self.repo_owner = repo_owner or settings.GITHUB_REPO_OWNER
        self.repo_name = repo_name or settings.GITHUB_REPO_NAME
        self.version = version or self._determine_next_version()
    
    def _determine_next_version(self):
        """
        Determine the next version based on existing DocumentationEntry objects
        Uses semantic versioning: MAJOR.MINOR.PATCH
        """
        try:
            # Get the latest changelog entry
            latest_entry = DocumentationEntry.objects.filter(
                doc_type='changelog'
            ).order_by('-created').first()
            
            if not latest_entry:
                return "0.1.0"  # Default initial version
            
            # Extract version from title
            import re
            version_match = re.search(r'v?(\d+\.\d+\.\d+)', latest_entry.title)
            if not version_match:
                return "0.1.0"
            
            # Parse version
            version = version_match.group(1)
            major, minor, patch = map(int, version.split('.'))
            
            # Increment patch version
            new_version = f"{major}.{minor}.{patch + 1}"
            return new_version
            
        except Exception as e:
            logger.error(f"Error determining next version: {e}")
            return "0.1.0"
        
    def fetch_recent_commits(self, days=1, branch=None):
        """
        Fetch commits from the past N days
        
        Args:
            days (int): Number of days to look back
            branch (str, optional): Specific branch to check
            
        Returns:
            list: List of commit objects
        """
        since_date = datetime.now() - timedelta(days=days)

        logger.info(f"Fetching commits since {since_date} for {self.repo_owner}/{self.repo_name}")
        
        commits = self.github_client.get_repository_commits(
            owner=self.repo_owner,
            repo_name=self.repo_name,
            since=since_date,
            branch=branch
        )
        
        logger.info(f"Fetched {len(commits)} commits from {self.repo_owner}/{self.repo_name}")
        return commits
    
    def analyze_commit_changes(self, commit):
        """
        Analyze changes made in a specific commit
        
        Args:
            commit: GitHub commit object
            
        Returns:
            dict: Analysis of the commit changes
        """
        commit_files = self.github_client.get_commit_files(
            owner=self.repo_owner,
            repo_name=self.repo_name,
            commit_sha=commit.sha
        )
        
        commit_stats = self.github_client.get_commit_stats(
            owner=self.repo_owner,
            repo_name=self.repo_name,
            commit_sha=commit.sha
        )
        
        # Categorize file changes
        file_categories = {
            'added': [],
            'modified': [],
            'removed': [],
            'renamed': []
        }
        
        extensions = {}
        directories = {}
        
        for file in commit_files:
            # Categorize by change type
            file_categories[file.status].append(file.filename)
            
            # Count file extensions
            ext = file.filename.split('.')[-1] if '.' in file.filename else 'no_extension'
            extensions[ext] = extensions.get(ext, 0) + 1
            
            # Count directories
            directory = file.filename.split('/')[0] if '/' in file.filename else 'root'
            directories[directory] = directories.get(directory, 0) + 1
        
        return {
            'commit_sha': commit.sha,
            'commit_message': commit.commit.message,
            'author': commit.commit.author.name,
            'date': commit.commit.author.date.isoformat(),
            'stats': commit_stats,
            'file_categories': file_categories,
            'extensions': extensions,
            'directories': directories,
            'files': [f.filename for f in commit_files]
        }
    
    def generate_commit_summary(self, commits):
        """
        Generate a summary of commits for social media
        
        Args:
            commits: List of GitHub commit objects
            
        Returns:
            dict: Summary content for different platforms
        """
        if not commits:
            return None
            
        # Analyze all commits
        detailed_analyses = []
        total_additions = 0
        total_deletions = 0
        affected_directories = set()
        file_extensions = {}
        
        for commit in commits[:10]:  # Limit to 10 commits for analysis
            analysis = self.analyze_commit_changes(commit)
            detailed_analyses.append(analysis)
            
            # Aggregate stats
            if 'stats' in analysis:
                total_additions += analysis['stats'].get('additions', 0)
                total_deletions += analysis['stats'].get('deletions', 0)
            
            # Track affected directories and file types
            for directory in analysis.get('directories', {}):
                affected_directories.add(directory)
                
            for ext, count in analysis.get('extensions', {}).items():
                file_extensions[ext] = file_extensions.get(ext, 0) + count
        
        # Create the content
        commit_count = len(commits)
        timeframe = "today" if commit_count == 1 else f"the past {len(commits)} commits"
        
        # For longer formats (blog, README)
        body = f"""## Latest Code Updates

In {timeframe}, we've made {commit_count} commits to the Fartemis project, with {total_additions} lines added and {total_deletions} lines removed.

### Key Changes:
"""
        
        # Add bullet points for each commit
        for analysis in detailed_analyses:
            commit_message = analysis['commit_message'].split('\n')[0]
            commit_hash = analysis['commit_sha'][:7]
            body += f"- {commit_message} ({commit_hash})\n"
        
        body += f"""
### Summary

These changes affected {len(affected_directories)} directories, primarily working with {", ".join(sorted(file_extensions, key=lambda x: file_extensions[x], reverse=True)[:3])} files.
"""
        
        # For Bluesky (300 char limit)
        short_content = f"📊 Fartemis update: {commit_count} new commits with +{total_additions}/-{total_deletions} lines. Working on {', '.join(list(affected_directories)[:2])}. #Python #OpenSource #JobHunting"
        
        # For Twitter (280 char limit)
        micro_content = f"📊 Fartemis: {commit_count} commits, +{total_additions}/-{total_deletions} lines. #Python #OpenSource #JobHunting"
        
        # Return content for different platforms
        return {
            'title': f"Fartemis Development Update: {commit_count} New Commits",
            'body': body,
            'short_content': short_content,
            'micro_content': micro_content,
            'hashtags': ['Python', 'OpenSource', 'JobHunting', 'AI', 'Development'],
            'detailed_analyses': detailed_analyses
        }
    

    def generate_documentation(self, commits):
        """
        Generate documentation for the CHANGELOG.md file using semantic versioning
        
        Args:
            commits: List of GitHub commit objects
            
        Returns:
            str: Markdown changelog entry
        """
        if not commits:
            return None
            
        summary = self.generate_commit_summary(commits)
        if not summary:
            return None
        
        # Get the current date for the changelog entry
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Create a changelog entry with version
        markdown = f"""## [v{self.version}] - {today}

### Added/Changed
"""
        
        # Add bullet points for each commit with their changes
        for analysis in summary['detailed_analyses']:
            # Get first line of commit message
            message = analysis['commit_message'].split('\n')[0]
            # Add bullet point with commit message and link to commit
            markdown += f"- {message} ([{analysis['commit_sha'][:7]}](https://github.com/{self.repo_owner}/{self.repo_name}/commit/{analysis['commit_sha']}))\n"
        
        # Add stats summary
        total_additions = sum(a['stats'].get('additions', 0) for a in summary['detailed_analyses'])
        total_deletions = sum(a['stats'].get('deletions', 0) for a in summary['detailed_analyses'])
        
        markdown += f"\n{total_additions} additions and {total_deletions} deletions across {len(commits)} commits\n\n"
        
        return markdown


    def create_content_from_commits(self, days=1, branch=None):
        """
        Check for recent commits and create content
        
        Args:
            days (int): Number of days to look back
            branch (str, optional): Branch to check
            
        Returns:
            tuple: (PublishContent object, documentation string)
        """
        # Fetch commits
        commits = self.fetch_recent_commits(days=days, branch=branch)
        
        if not commits:
            logger.info(f"No new commits found for {self.repo_owner}/{self.repo_name}")
            return None, None
        
        # Generate summary content
        summary = self.generate_commit_summary(commits)
        
        if not summary:
            logger.error("Failed to generate commit summary")
            return None, None
        
        # Generate documentation
        documentation = self.generate_documentation(commits)
        
        # Create PublishContent object
        content = PublishContent(
            title=summary['title'],
            body=summary['body'],
            short_content=summary['short_content'],
            micro_content=summary['micro_content'],
            content_type=ContentType.COMMIT_SUMMARY,
            hashtags=summary['hashtags'],
            origin_type=ContentOrigin.GITHUB,
            origin_id=commits[0].sha,  # Use the most recent commit SHA
            status=ContentStatus.READY
        )
        
        # Save to database
        try:
            content.save()
            logger.info(f"Created new publish content: {content.id}")
            return content, documentation
        except Exception as e:
            logger.error(f"Failed to save publish content: {str(e)}")
            return None, None
        
