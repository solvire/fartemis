import os
import json
import logging
import re

import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup

from typing import List, Dict, Any, Optional
from langchain_tavily import TavilySearch
from langchain.chat_models import init_chat_model
from langgraph.prebuilt import create_react_agent
from django.utils import timezone
from django.conf import settings
from langsmith import Client
import langsmith

from .models import CompanyProfile, CompanyResearchReferences, CompanyResearchLog
from .constants import CompanyReviewSentiment, COUNTRY_CODE_MAPPING

logger = logging.getLogger(__name__)

class CompanyResearchController:
    """Controller for company research operations"""
    
    def __init__(self):
        """Initialize the controller with necessary API clients"""
        # Make sure environment variables are set
        assert settings.TAVILY_API_KEY, "Tavily API key not found"
        assert settings.ANTHROPIC_API_KEY, "Anthropic API key not found"
        assert settings.LANGCHAIN_API_KEY, "LangChain API key not found"
        assert settings.LANGCHAIN_PROJECT, "LangChain project name not found"
        
        # Initialize LangSmith client
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.LANGCHAIN_API_KEY
        os.environ["LANGCHAIN_PROJECT"] = settings.LANGCHAIN_PROJECT
        os.environ["CLAUDE_MODEL"] = settings.CLAUDE_MODEL_SMALL
        
        self.langsmith_client = Client()
        
        # Initialize LLM
        self.llm = init_chat_model(settings.CLAUDE_MODEL, model_provider="anthropic")
        
        # Initialize Tavily search tool
        self.tavily_search_tool = TavilySearch(
            max_results=10,
            topic="general",
            search_depth="advanced",
        )
        
        # Create React agent
        self.agent = create_react_agent(self.llm, [self.tavily_search_tool])
    
    def research_company(self, company_id: int) -> CompanyProfile:
        """
        Research a company using the React agent with Tavily search
        
        Args:
            company_id: ID of the company to research
            
        Returns:
            Updated company profile
        """
        # Get company profile
        company = CompanyProfile.objects.get(id=company_id)
        
        # Build research query
        query = self._build_research_query(company)
        
        # Create LangSmith run
        with langsmith.trace(
            project_name=settings.LANGCHAIN_PROJECT,
            name=f"Company Research: {company.name}",
            tags=["company_research", f"company_{company.id}"]
        ) as run:
            # Add company metadata to the run
            run.add_metadata({
                "company_id": company.id,
                "company_name": company.name,
                "research_type": "company_profile"
            })
            
            # Execute research
            research_result, references = self._execute_research(query)
            
            # Store AI analysis
            company.ai_analysis = research_result
            company.last_sentiment_update = timezone.now()
            company.save()
            
            # Extract and save references
            self._save_references(company, references)
            
            # Log research activity
            self._log_research(company, research_result)
            
            # Extract structured data and update profile
            self._update_profile_from_analysis(company, research_result, references)  # Pass references here
            
            # Add result summary to the run
            run.add_metadata({
                "references_count": len(references),
                "analysis_length": len(research_result)
            })
        
        return company
    
    def _build_research_query(self, company: CompanyProfile) -> str:
        """
        Build a comprehensive research query based on company details
        """
        location_info = ""
        if company.headquarters_city and company.headquarters_state:
            location_info = f" in {company.headquarters_city}, {company.headquarters_state}, {company.headquarters_country}"
        
        query = f"""
I need a comprehensive company profile on {company.name}{location_info}.
You are going to help me understand the type of company and culture as if I am evaluating working for that organization.

Please include:
- Company overview, history, and leadership
- Core business and products/services
- Company culture and work environment
- Growth and market position
- Work-life balance based on employee reviews
- Potential challenges of working there
- Location considerations

Include specific details that would help someone evaluate this company as a potential employer.
"""
        
        return query
    
    def _execute_research(self, query: str) -> tuple:
        """
        Execute research using React agent and extract references
        
        Returns:
            Tuple of (final_result, references)
        """
        # Track references during search
        references = []
        
        # Execute agent with tracing
        with langsmith.trace(
            name="React Agent Execution",
            run_type="chain"
        ) as run:
            # Add query metadata
            run.add_metadata({
                "query": query,
                "tool": "tavily_search"
            })
            
            # Execute the agent
            agent_execution = self.agent.invoke({"messages": query})
            
            # Extract the final answer
            final_result = agent_execution['messages'][-1].content
            
            # Extract references from intermediate steps
            steps = agent_execution.get('intermediate_steps', [])
            for step in steps:
                # Check if this is a tool call
                if step and isinstance(step, list) and len(step) >= 2:
                    action = step[0]
                    observation = step[1]
                    
                    # Check if the action is a tool call to tavily
                    if hasattr(action, 'tool') and action.tool == 'tavily_search_tool':
                        # Get the tool output which contains the search results
                        if observation:
                            try:
                                # Observation might be a string or dictionary, handle both
                                results = observation
                                if isinstance(observation, str):
                                    try:
                                        results = json.loads(observation)
                                    except:
                                        # If it's not JSON, store the raw text
                                        references.append({
                                            "title": "Search Result",
                                            "url": "N/A",
                                            "content": observation,
                                            "query": action.tool_input.get('query', '')
                                        })
                                        continue
                                
                                # Extract references
                                if isinstance(results, list):
                                    for result in results:
                                        if isinstance(result, dict) and 'url' in result:
                                            references.append({
                                                "title": result.get("title", ""),
                                                "url": result.get("url", ""),
                                                "content": result.get("content", ""),
                                                "query": action.tool_input.get('query', '')
                                            })
                            except Exception as e:
                                print(f"Error extracting search results: {e}")
                                run.add_metadata({
                                    "error": str(e),
                                    "error_type": "reference_extraction"
                                })
            
            # Add results metadata
            run.add_metadata({
                "references_count": len(references),
                "result_length": len(final_result)
            })
        
        return final_result, references

    def _find_careers_page(self, company: CompanyProfile, references: List[Dict[str, str]]) -> str:
        """
        Find the careers page URL for a company from references or by searching
        """
        with langsmith.trace(
            name="Find Careers Page",
            run_type="chain"
        ) as run:
            # First, check if we already have it
            if company.careers_page_url:
                return company.careers_page_url
            
            # Try hierarchical URL patterns first if we have a website
            if company.website:
                careers_url = self._try_common_careers_patterns(company.website, company.name)
                if careers_url:
                    run.add_metadata({
                        "source": "pattern_matching",
                        "url": careers_url
                    })
                    return careers_url
            
            # Check if it's in the references we already have
            for ref in references:
                content = ref.get("content", "").lower()
                url = ref.get("url", "").lower()
                title = ref.get("title", "").lower()
                
                careers_keywords = ["careers", "jobs", "work with us", "join us", "career", "job openings"]
                
                # Check if URL or title contains careers keywords
                is_careers_page = any(keyword in url for keyword in careers_keywords) or \
                                any(keyword in title for keyword in careers_keywords)
                
                # Check if it's on the company's official domain
                is_official_domain = False
                if company.website:
                    company_domain = self._extract_domain(company.website)
                    url_domain = self._extract_domain(url)
                    is_official_domain = company_domain == url_domain
                
                # Check if it's NOT a specific job listing
                # Job listings often have numerical IDs at the end of the URL
                is_specific_job = bool(re.search(r'/jobs/\d+', url)) or bool(re.search(r'/careers/\d+', url))
                
                # Only return if it's a careers page AND on official domain AND not a specific job listing
                if is_careers_page and is_official_domain and not is_specific_job:
                    run.add_metadata({
                        "source": "references",
                        "url": url,
                        "is_official": is_official_domain
                    })
                    return url
            
            # If pattern matching and references fail, search specifically for careers page
            # Use more specific query to prioritize official company pages
            query = f"{company.name} official careers jobs listings page"
            
            try:
                search_results = self.tavily_search_tool.invoke(query)
                
                # Handle different response formats
                results_to_process = self._normalize_search_results(search_results)
                
                # Filter and score results to prioritize actual job pages over informational pages
                scored_results = []
                for result in results_to_process:
                    # Skip if not a dictionary
                    if not isinstance(result, dict):
                        continue
                    
                    url = result.get("url", "").lower()
                    title = result.get("title", "").lower()
                    content = result.get("content", "").lower()
                    
                    # Skip URLs that look like specific job listings
                    is_specific_job = bool(re.search(r'/jobs/\d+', url)) or bool(re.search(r'/careers/\d+', url))
                    if is_specific_job:
                        continue
                    
                    # Calculate score based on URL and title matches
                    score = 0
                    
                    # Check if it's on the company's official domain (highest priority)
                    is_official_domain = False
                    if company.website:
                        company_domain = self._extract_domain(company.website)
                        url_domain = self._extract_domain(url)
                        
                        # If it's the official company domain, give it a high score
                        if company_domain == url_domain:
                            is_official_domain = True
                            score += 50  # Much higher weight for official domain
                    
                    # Heavily penalize job board domains
                    job_board_domains = ["indeed.com", "linkedin.com", "glassdoor.com", "monster.com", 
                                        "careerbuilder.com", "ziprecruiter.com", "simplyhired.com",
                                        "dice.com", "theladders.com"]
                    
                    if any(board in url for board in job_board_domains):
                        score -= 30  # Strong penalty for job boards
                    
                    # Look for ideal URL patterns
                    if re.search(r'/careers/jobs/?$', url) or re.search(r'/site/[^/]+/careers/jobs/?$', url):
                        score += 20  # Highest score for the ideal pattern
                    elif '/careers/jobs' in url:
                        score += 15  # High score for variations of careers/jobs
                    elif re.search(r'/jobs/?$', url):
                        score += 10  # Good score for /jobs endpoint
                    elif re.search(r'/careers/?$', url):
                        score += 5   # Lower score for general careers page
                    
                    # Add to scored results if score is positive
                    if score > 0:
                        scored_results.append((score, url, is_official_domain))
                
                # Sort by score (descending)
                scored_results.sort(reverse=True)
                
                # Return the highest scored URL if any found
                if scored_results:
                    best_url = scored_results[0][1]
                    is_official = scored_results[0][2]
                    
                    # Clean up the URL by removing any specific job ID
                    if re.search(r'/jobs/\d+', best_url):
                        best_url = re.sub(r'/jobs/\d+.*', '/jobs', best_url)
                    if re.search(r'/careers/jobs/\d+', best_url):
                        best_url = re.sub(r'/jobs/\d+.*', '', best_url)
                    
                    run.add_metadata({
                        "source": "scored_search_results",
                        "url": best_url,
                        "score": scored_results[0][0],
                        "is_official": is_official
                    })
                    return best_url
                
                # If still not found, use LLM to help
                careers_prompt = f"""
Based on this company information, what is the most likely URL for their official job listings page?

Company: {company.name}
Website: {company.website or 'Unknown'}

Please provide ONLY the URL for the main job listings page, not for any specific job posting.
For example, a good URL would be "company.com/careers/jobs" and not "company.com/careers/jobs/12345".

Provide just the URL and nothing else.
"""
                
                response = self.llm.invoke(careers_prompt)
                suggested_url = response.content.strip()
                
                # Validate that the suggested URL is not a specific job listing
                is_specific_job = bool(re.search(r'/jobs/\d+', suggested_url)) or bool(re.search(r'/careers/\d+', suggested_url))
                if is_specific_job:
                    # Clean up the URL by removing any specific job ID
                    if re.search(r'/jobs/\d+', suggested_url):
                        suggested_url = re.sub(r'/jobs/\d+.*', '/jobs', suggested_url)
                    if re.search(r'/careers/jobs/\d+', suggested_url):
                        suggested_url = re.sub(r'/jobs/\d+.*', '', suggested_url)
                
                run.add_metadata({
                    "source": "llm_suggestion",
                    "url": suggested_url
                })
                
                # Basic validation
                if suggested_url.startswith('http') and '.' in suggested_url:
                    return suggested_url
                
            except Exception as e:
                logger.error(f"Error finding careers page: {e}")
                run.add_metadata({
                    "error": str(e)
                })
            
            return None



    def _normalize_search_results(self, search_results):
        """Helper to normalize different search result formats"""
        results_to_process = []
        
        # Check if search_results is a dictionary (single result or metadata container)
        if isinstance(search_results, dict):
            # If it has a 'results' key, use that
            if 'results' in search_results:
                results_to_process = search_results.get('results', [])
            # Otherwise, treat the dictionary itself as a single result
            else:
                results_to_process = [search_results]
        # Check if search_results is a list (multiple results)
        elif isinstance(search_results, list):
            results_to_process = search_results
        else:
            # If it's neither dict nor list, log the unexpected type
            logger.warning(f"Unexpected search_results type: {type(search_results)}")
        
        return results_to_process
    



    def _extract_domain(self, url: str) -> str:
        """
        Extract the base domain from a URL
        """
        try:
            # Parse the URL
            parsed = urlparse(url)
            
            # Get the netloc (domain with subdomains)
            domain = parsed.netloc
            
            # Remove www. if present
            if domain.startswith('www.'):
                domain = domain[4:]
            
            # Get the base domain (e.g., example.com from subdomain.example.com)
            domain_parts = domain.split('.')
            
            # Handle special cases like .co.uk, .com.au, etc.
            if len(domain_parts) > 2 and domain_parts[-2] in ['co', 'com', 'org', 'net', 'gov', 'edu', 'ac']:
                # For domains like example.co.uk
                if len(domain_parts) > 3:
                    return '.'.join(domain_parts[-3:])
                return '.'.join(domain_parts[-2:])
            
            # Standard case: return last two parts (example.com)
            if len(domain_parts) > 1:
                return '.'.join(domain_parts[-2:])
            
            return domain
        except Exception:
            return url


    def _try_common_careers_patterns(self, website: str, company_name: str) -> Optional[str]:
        """
        Try common patterns for careers pages before searching
        """
        # Extract domain from website
        try:
            parsed_url = urlparse(website)
            domain = parsed_url.netloc
            
            # Remove www. if present
            if domain.startswith('www.'):
                domain = domain[4:]
            
            # Create base domain without subdomains
            domain_parts = domain.split('.')
            if len(domain_parts) > 2:
                base_domain = '.'.join(domain_parts[-2:])
            else:
                base_domain = domain
            
            # Create a session for requests
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            })
            
            # Try common career subdomain patterns first (highest priority)
            subdomain_patterns = [
                f"https://careers.{base_domain}/jobs",
                f"https://careers.{base_domain}",
                f"https://jobs.{base_domain}",
                f"https://work.{base_domain}",
                f"https://careers.{domain}",
                f"https://jobs.{domain}",
            ]
            
            # Check each subdomain pattern
            for url in subdomain_patterns:
                try:
                    response = session.get(url, timeout=5)
                    if response.status_code == 200:
                        return url
                except Exception:
                    continue
            
            # Try standard path patterns on main domain
            path_patterns = [
                f"{website.rstrip('/')}/jobs",
                f"{website.rstrip('/')}/careers/jobs",
                f"{website.rstrip('/')}/careers",
                f"{website.rstrip('/')}/work-with-us",
                f"{website.rstrip('/')}/join-us",
            ]
            
            # Check each path pattern
            for url in path_patterns:
                try:
                    response = session.get(url, timeout=5)
                    if response.status_code == 200:
                        return url
                except Exception:
                    continue
            
            # If main patterns don't work, try to find links on the main careers page
            try:
                careers_url = f"{website.rstrip('/')}/careers"
                response = session.get(careers_url, timeout=5)
                
                if response.status_code == 200:
                    # Look for links to job listings
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Look for job-related links
                    job_keywords = ['jobs', 'openings', 'positions', 'listings']
                    
                    for link in soup.find_all('a', href=True):
                        link_text = link.text.lower()
                        href = link['href']
                        
                        # Check if link contains job keywords
                        if any(keyword in link_text for keyword in job_keywords):
                            # Handle relative URLs
                            if href.startswith('/'):
                                href = f"{parsed_url.scheme}://{parsed_url.netloc}{href}"
                            elif not href.startswith('http'):
                                href = f"{website.rstrip('/')}/{href.lstrip('/')}"
                            
                            return href
            except Exception:
                pass
            
        except Exception as e:
            logger.error(f"Error trying common patterns: {str(e)}")
        
        return None


    def _convert_to_country_code(self, country_name: str) -> str:
        """
        Convert a country name to its 2-letter ISO code
        """
        if not country_name:
            return None
            
        # Normalize the country name
        normalized = country_name.lower().strip()
        
        # Check if it's already a 2-letter code
        if len(normalized) == 2 and normalized.isalpha():
            return normalized.upper()
            
        # Check our mapping
        if normalized in COUNTRY_CODE_MAPPING:
            return COUNTRY_CODE_MAPPING[normalized]
            
        # If not found, ask LLM (for non-standard country names)
        try:
            country_prompt = f"""
Convert this country name to its 2-letter ISO country code (ISO 3166-1 alpha-2):

Country: {country_name}

Respond with ONLY the 2-letter code in uppercase.
"""
            
            response = self.llm.invoke(country_prompt)
            code = response.content.strip().upper()
            
            # Basic validation
            if len(code) == 2 and code.isalpha():
                return code
        except Exception as e:
            print(f"Error converting country name: {e}")
        
        # If all else fails, return the original
        return country_name

    def _save_references(self, company: CompanyProfile, references: List[Dict[str, str]]) -> None:
        """
        Save extracted references to CompanyResearchReferences
        """
        # Default sentiment
        default_sentiment = "neutral"
        
        with langsmith.trace(
            name="Save References",
            run_type="chain"
        ) as run:
            created_refs = []
            for ref in references:
                # Extract potential title from content if title is empty
                title = ref.get("title", "")
                if not title and ref.get("content"):
                    # Try to extract a title from the first line or sentence
                    content = ref.get("content", "")
                    first_line = content.split('\n')[0]
                    if len(first_line) > 10 and len(first_line) < 100:
                        title = first_line
                    else:
                        first_sentence = content.split('.')[0]
                        if len(first_sentence) > 10 and len(first_sentence) < 100:
                            title = first_sentence
                        else:
                            title = content[:100] + "..." if len(content) > 100 else content
                
                # Add the query to the content for context
                content = ref.get("content", "")
                query = ref.get("query", "")
                if query:
                    content = f"Search Query: {query}\n\n{content}"
                
                # Create reference
                ref_obj = CompanyResearchReferences.objects.create(
                    company=company,
                    title=title or "Untitled Reference",
                    url=ref.get("url", "N/A"),
                    content=content,
                    sentiment=default_sentiment
                )
                created_refs.append(ref_obj.id)
            
            run.add_metadata({
                "company_id": company.id,
                "references_count": len(created_refs),
                "reference_ids": created_refs
            })
    

    def _log_research(self, company: CompanyProfile, research_result: str) -> None:
        """
        Log the research activity
        """
        with langsmith.trace(
            name="Log Research",
            run_type="chain"
        ):
            log = CompanyResearchLog.objects.create(
                company=company,
                content=research_result
            )
    
    def _update_profile_from_analysis(self, company: CompanyProfile, analysis: str, references: List[Dict[str, str]]) -> None:
        """
        Extract structured data from analysis and update the company profile
        """
        with langsmith.trace(
            name="Extract Structured Data",
            run_type="chain"
        ) as run:
            # Use LLM to extract structured data
            extraction_prompt = f"""
            Based on the following company analysis, extract structured data for database storage.
            
            COMPANY ANALYSIS:
            {analysis}
            
            Return a JSON object with the following fields (leave empty if information is not available):
            {{
                "description": "Brief company description",
                "founded_year": 0000,
                "employee_count_min": 0,
                "employee_count_max": 0,
                "headquarters_city": "",
                "headquarters_state": "",
                "headquarters_country": "",
                "is_public": true/false,
                "stock_symbol": "",
                "funding_status": "",
                "glassdoor_rating": 0.0,
                "indeed_rating": 0.0,
                "employee_sentiment_score": 0.0,
                "sentiment_summary": ""
            }}
            """
            
            # Get structured data
            response = self.llm.invoke(extraction_prompt)
            
            try:
                # Extract JSON from response
                json_str = response.content
                
                # If the response contains markdown code blocks, extract JSON from them
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0].strip()
                elif "```" in json_str:
                    json_str = json_str.split("```")[1].split("```")[0].strip()
                
                data = json.loads(json_str)
                
                # Log extracted data
                run.add_metadata({
                    "extracted_data": data
                })
                
                # Update company fields with extracted data
                if data.get("description"):
                    company.description = data["description"]
                    
                if data.get("founded_year"):
                    company.founded_year = data["founded_year"]
                    
                if data.get("employee_count_min"):
                    company.employee_count_min = data["employee_count_min"]
                    
                if data.get("employee_count_max"):
                    company.employee_count_max = data["employee_count_max"]
                    
                if data.get("headquarters_city"):
                    company.headquarters_city = data["headquarters_city"]
                    
                if data.get("headquarters_state"):
                    company.headquarters_state = data["headquarters_state"]
                    
                if data.get("headquarters_country"):
                    country_name = data["headquarters_country"]
                    company.headquarters_country = self._convert_to_country_code(country_name)
                    
                if data.get("is_public") is not None:
                    company.is_public = data["is_public"]
                    
                if data.get("stock_symbol"):
                    company.stock_symbol = data["stock_symbol"]
                    
                if data.get("funding_status"):
                    company.funding_status = data["funding_status"]
                    
                if data.get("glassdoor_rating"):
                    company.glassdoor_rating = data["glassdoor_rating"]
                    
                if data.get("indeed_rating"):
                    company.indeed_rating = data["indeed_rating"]
                    
                if data.get("employee_sentiment_score"):
                    company.employee_sentiment_score = data["employee_sentiment_score"]
                    
                if data.get("sentiment_summary"):
                    if not company.sentiment_data_points:
                        company.sentiment_data_points = {}
                    
                    company.sentiment_data_points["summary"] = data["sentiment_summary"]
                
                # Find careers page URL
                careers_url = self._find_careers_page(company, references)
                if careers_url:
                    company.careers_page_url = careers_url
                
                company.save()
                
                run.add_metadata({
                    "company_updated": True,
                    "updated_fields": list(data.keys()) + (["careers_page_url"] if careers_url else [])
                })
                
            except Exception as e:
                error_msg = f"Error extracting structured data: {e}"
                print(error_msg)
                run.add_metadata({
                    "error": error_msg,
                    "company_updated": False
                })