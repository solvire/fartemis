import os
import json
import logging
import re

import time
import random

import requests
from urllib.parse import urlparse, urljoin, unquote
from bs4 import BeautifulSoup

from typing import List, Dict, Any, Optional, Tuple

from langchain.chat_models import init_chat_model
from langgraph.prebuilt import create_react_agent
from django.utils import timezone
from django.conf import settings
from langsmith import Client
import langsmith

from langchain_tavily import TavilySearch
from langchain.agents import create_react_agent
from langchain_anthropic import ChatAnthropic
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools.render import format_tool_to_openai_function
from langchain_core.utils.function_calling import convert_to_openai_function
from langchain.agents.format_scratchpad import format_to_openai_function_messages
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain.agents import initialize_agent, AgentType, AgentExecutor, create_react_agent
from langchain.agents.output_parsers import OpenAIFunctionsAgentOutputParser
from langchain.tools import tool
from langchain.chains.summarize import load_summarize_chain
from langsmith import Client
import langsmith

from fartemis.companies.models import CompanyProfile, CompanyRole, UserCompanyAssociation
from fartemis.jobboards.models import Job
from fartemis.users.models import User, ContactMethodType, UserContactMethod, UserSourceLink
from fartemis.llms.clients import LLMClientFactory, LLMProvider



from langchain.agents import AgentExecutor, tool

from .models import CompanyProfile, CompanyResearchReferences, CompanyResearchLog
from .constants import CompanyReviewSentiment, COUNTRY_CODE_MAPPING


logger = logging.getLogger(__name__)

try:
    from thefuzz import fuzz
    thefuzz_available = True
except ImportError:
    thefuzz_available = False
    logger.warning("The 'thefuzz' library is not installed. Company name matching will be exact. Install with: pip install thefuzz[speedup]")


try:
    from tavily import TavilyClient
    # Assuming TavilyClient is the correct class as per Tavily's newer usage
    # If you were using Langchain's TavilySearch, the import would be different.
    # Adjust based on your actual Tavily library usage.
    tavily_available = True
except ImportError:
    tavily_available = False
    TavilyClient = None # Define as None if not available



# Constants for company size
SIZE_SMALL = 'small'
SIZE_MEDIUM = 'medium'
SIZE_LARGE = 'large'
SIZE_UNKNOWN = 'unknown'


class CompanyResearchController:
    """Controller for company research operations"""
    
    def __init__(self, llm=None, tavily_search=None, langsmith_client=None):
        """
        Initialize the controller with necessary API clients
        
        Args:
            llm: Language model instance (defaults to Claude if None)
            tavily_search: Search tool instance (defaults to TavilySearch if None)
            langsmith_client: LangSmith client for tracing (defaults to Client() if None)
        """
        # Initialize LangSmith client
        self.langsmith_client = langsmith_client or Client()
        
        # Initialize LLM
        if llm is None:
            # Default to Claude
            self.llm = init_chat_model("claude-3-7-latest", model_provider="anthropic")
        else:
            self.llm = llm
        
        # Initialize Tavily search tool
        if tavily_search is None:
            self.tavily_search_tool = TavilySearch(
                max_results=10,
                topic="general",
                search_depth="advanced",
            )
        else:
            self.tavily_search_tool = tavily_search
        
        # Create React agent with the provided or default LLM
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
                
                # data = json.loads(json_str)
                data = self._extract_json_from_llm_response(response.content)
                
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

    def _extract_json_from_llm_response(self, response_content):
        """Extract JSON from LLM response, handling differences between models"""
        # Extract JSON from response
        json_str = response_content
        
        # If the response contains markdown code blocks, extract JSON from them
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()
        
        # Remove any extra text before or after the JSON object
        json_str = json_str.strip()
        if json_str.startswith("{") and "}" in json_str:
            # Extract just the JSON object
            json_str = json_str[:json_str.rindex("}")+1]
        
        return json.loads(json_str)
    




####### Employee Research Controller #########


class LinkedInProfileFinder:
    """
    Class for finding LinkedIn profiles for people based on name and company.
    Uses web search (DuckDuckGo, Tavily) and page analysis to find the best match.
    """

    MAX_SCORE = 24.0 # Max potential score: Name URL (10) + First Name Context (3) + Last Name Context (3) + Company Context (8)

    def __init__(self, verbose=False):
        self.verbose = verbose
        # Logging configured elsewhere

    # ... (find_profile method remains the same) ...
    def find_profile(self, first_name, last_name, company=None, search_engine='both', max_pages=5):
        # ... (No changes needed in this method itself) ...
        if not first_name or not last_name:
             logger.error("First name and last name are required.")
             return None

        logger.info(f"Searching for LinkedIn profile of {first_name} {last_name}")
        if company:
            logger.info(f"Associated with company: {company}")

        # --- Step 1: Perform web search ---
        search_results = []
        if search_engine in ['duckduckgo', 'both']:
            logger.info("Using DuckDuckGo search...")
            # *** We will call the MODIFIED _perform_duckduckgo_search below ***
            try:
                duckduckgo_results = self._perform_duckduckgo_search(first_name, last_name, company)
                search_results.extend(duckduckgo_results)
                logger.info(f"Found {len(duckduckgo_results)} results via DuckDuckGo.")
            except requests.exceptions.RequestException as e:
                 # Handle specific request errors gracefully here if desired,
                 # or let them propagate if _perform_duckduckgo_search re-raises.
                 # Current _perform_duckduckgo_search handles RequestException internally.
                 logger.error(f"DuckDuckGo search request failed (handled): {e}")
            except Exception as e:
                 # Catch other potential errors from DDG function if they weren't handled
                 logger.error(f"Unexpected error during DuckDuckGo search processing: {e}", exc_info=self.verbose)


        if search_engine in ['tavily', 'both']:
             if not tavily_available:
                 logger.warning("Tavily client not available/installed. Skipping Tavily search.")
             elif not getattr(settings, 'TAVILY_API_KEY', None):
                 logger.warning("TAVILY_API_KEY not found in settings. Skipping Tavily search.")
             else:
                logger.info("Using Tavily search...")
                try:
                    tavily_results = self._perform_tavily_search(first_name, last_name, company)
                    search_results.extend(tavily_results)
                    logger.info(f"Found {len(tavily_results)} results via Tavily.")
                except Exception as e:
                    logger.error(f"Tavily search failed: {e}", exc_info=self.verbose)

        if not search_results:
            logger.warning("No search results found from any engine.")
            return None

        # --- Step 2: Prioritize pages ---
        prioritized_pages = self._prioritize_pages(search_results, first_name, last_name, company)
        if not prioritized_pages:
             logger.warning("No pages could be prioritized from search results.")
             return None

        # --- Step 3 & 4: Analyze pages and Rank (No changes needed here) ---
        # ... (rest of find_profile method is unchanged) ...
        potential_profiles = {}
        pages_analyzed = 0

        logger.info(f"Analyzing up to {max_pages} prioritized pages...")
        for page in prioritized_pages:
            if pages_analyzed >= max_pages:
                logger.info(f"Reached max_pages limit ({max_pages}).")
                break

            url = page['url']
            priority = page['priority']
            reason = page['reason']
            is_direct_profile_url = 'linkedin.com/in/' in url

            logger.info(f"Analyzing page #{pages_analyzed + 1}: {url} (Priority: {priority:.1f}, Reason: {reason})")

            if is_direct_profile_url:
                profile_handle = self._extract_handle_from_url(url)
                if profile_handle:
                    clean_url = self._clean_profile_url(url)
                    match_score = self._calculate_profile_match_score(url, "", first_name, last_name, company)
                    if clean_url not in potential_profiles or match_score > potential_profiles[clean_url]['match']:
                         logger.info(f"Adding/Updating direct profile: {clean_url} (Match Score: {match_score:.1f} based on URL)")
                         potential_profiles[clean_url] = {
                            'url': clean_url,
                            'original_url': url,
                            'text': f"{first_name} {last_name}",
                            'context': "Direct profile URL from search",
                            'match': match_score,
                            'source_type': 'direct_url'
                        }
                    else:
                         logger.debug(f"Direct profile {clean_url} already found with equal/higher score.")
                    pages_analyzed += 1
                    continue

            page_content = self._fetch_page(url)
            if not page_content:
                pages_analyzed += 1
                continue

            page_profiles = self._extract_linkedin_profiles(page_content, first_name, last_name, company)
            if page_profiles:
                logger.info(f"Found {len(page_profiles)} potential LinkedIn profile links on page {url}")
                for profile in page_profiles:
                    clean_profile_url = self._clean_profile_url(profile['url'])
                    if clean_profile_url not in potential_profiles or profile['match'] > potential_profiles[clean_profile_url]['match']:
                        logger.debug(f"Adding/Updating extracted profile: {clean_profile_url} (Match Score: {profile['match']:.1f})")
                        potential_profiles[clean_profile_url] = {
                            **profile,
                            'url': clean_profile_url,
                            'original_url': profile['url'],
                            'source_type': 'extracted'
                        }
                    else:
                         logger.debug(f"Extracted profile {clean_profile_url} already found with equal/higher score.")
            else:
                logger.info(f"No LinkedIn profile links found on page {url}")
            pages_analyzed += 1

        if not potential_profiles:
            logger.warning("No potential LinkedIn profiles found after analyzing pages.")
            return None

        final_profiles = self._rank_profiles(list(potential_profiles.values()))
        best_profile = final_profiles[0]
        best_handle = self._extract_handle_from_url(best_profile['url'])

        if best_handle:
            logger.info(f"Best match found: {best_profile['url']} (Handle: {best_handle}, Score: {best_profile['match']:.1f}, Confidence: {best_profile['confidence']})")
            return {
                'handle': best_handle,
                'url': best_profile['url'],
                'confidence': best_profile['confidence'],
                'match_score': best_profile['match']
            }
        else:
             logger.error(f"Could not extract handle from the best match URL: {best_profile['url']}")
             return None
    # --- END of find_profile ---


    # vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
    # --- MODIFIED DuckDuckGo Search Function ---
    # vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
    def _perform_duckduckgo_search(self, first_name, last_name, company=None):
        """
        Perform a web search using DuckDuckGo HTML results.
        Handles network/HTTP errors but allows parsing errors to raise.
        Uses a slightly broader query.
        """
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://duckduckgo.com/',
        }

        # Construct search term - Simplified: Use quotes, add "linkedin", remove site: operator
        search_term = f'{first_name} {last_name}'
        if company:
            search_term += f' "{company}"'
        search_term += ' linkedin' # Rely on keyword instead of site: operator for html version
        encoded_query = requests.utils.quote(search_term)
        search_url = f"https://html.duckduckgo.com/html/?q={encoded_query}&kl=us-en"

        logger.debug(f"Attempting DDG Search URL: {search_url}")

        try:
            response = requests.get(search_url, headers=headers, timeout=15)
            logger.debug(f"DDG Response Status: {response.status_code}")
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

            # --- Parsing Logic - No broad Exception suppression here ---
            # If parsing fails below (e.g., structure change), it will raise an error.
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            raw_urls = []

            result_divs = soup.find_all('div', class_='result')
            logger.debug(f"Found {len(result_divs)} result divs in DDG HTML.")

            if not result_divs:
                logger.warning(f"DDG HTML parsing found no 'div.result' elements. HTML structure might have changed.")
                # Optional: Log response.text for manual inspection if verbose
                if self.verbose:
                    # Limit logged size to avoid flooding logs
                    log_limit = 2000
                    logged_text = response.text[:log_limit] + ('...' if len(response.text) > log_limit else '')
                    logger.debug(f"DDG Response Text (partial):\n{logged_text}")


            for i, result_div in enumerate(result_divs):
                logger.debug(f"Processing result div #{i+1}")
                title_a = result_div.find('a', class_='result__a')
                snippet_div = result_div.find('a', class_='result__snippet') # Note: This might be brittle, could be just text
                url_a = result_div.find('a', class_='result__url')

                # Use .select_one for potentially missing elements to avoid NoneType errors later
                # title_a = result_div.select_one('a.result__a')
                # snippet_div = result_div.select_one('div.result__snippet') # Snippets might be in divs now? Check HTML source
                # url_a = result_div.select_one('a.result__url')

                if title_a and url_a: # Snippet is less critical
                    title = title_a.get_text(strip=True)
                    href = title_a.get('href')
                    snippet = snippet_div.get_text(strip=True) if snippet_div else "[Snippet not found]"
                    logger.debug(f"  Raw href: {href}")

                    actual_url = None
                    if href and '/l/?uddg=' in href:
                         try:
                             parsed_href = urlparse(href)
                             # Robust parameter parsing
                             params = {}
                             if parsed_href.query:
                                 for qc in parsed_href.query.split('&'):
                                     if '=' in qc:
                                         key, val = qc.split('=', 1)
                                         params[key] = val # Takes the last value if key repeats
                             uddg_val = params.get('uddg')
                             if uddg_val:
                                actual_url = unquote(uddg_val)
                             else:
                                 logger.warning(f"  Found DDG redirect link but no 'uddg' param: {href}")
                                 actual_url = href # Fallback to the redirect itself
                         except Exception as decode_err:
                              logger.warning(f"  Error decoding DDG redirect URL {href}: {decode_err}")
                              actual_url = href # Fallback
                    elif href:
                         actual_url = urljoin(search_url, href) # Handle relative paths if any exist

                    logger.debug(f"  Title: {title}")
                    logger.debug(f"  Actual URL: {actual_url}")
                    logger.debug(f"  Snippet: {snippet[:100]}...") # Log partial snippet

                    if actual_url:
                        # Basic filter: Check if it looks like a plausible result
                        if 'linkedin.com' in actual_url.lower(): # Only add results pointing to LinkedIn
                            raw_urls.append(actual_url)
                            results.append({
                                'title': title,
                                'url': actual_url,
                                'snippet': snippet,
                                'source': 'duckduckgo'
                            })
                        else:
                             logger.debug(f"  Skipping non-LinkedIn URL: {actual_url}")
                else:
                    logger.warning(f"  Could not find expected elements (title_a, url_a) in result div #{i+1}. Skipping.")
                    if self.verbose:
                         logger.debug(f"  Problematic div HTML (partial): {str(result_div)[:500]}...")


            logger.debug(f"Raw qualifying DDG URLs found: {raw_urls}")
            if not results and result_divs:
                 logger.warning("Found result divs but extracted 0 valid results. Parsing logic likely needs update.")

            return results

        except requests.exceptions.RequestException as e:
            # Handle network/HTTP errors specifically
            logger.error(f"DuckDuckGo request failed: {e}")
            # Optionally: Log error details if verbose
            # if self.verbose:
            #     logger.error("RequestException Details:", exc_info=True)
            return [] # Return empty list on request failure
        # NO broad except Exception here - let other errors (like parsing errors) raise

    # --- END of MODIFIED DuckDuckGo Search Function ---
    # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^


    # ... (all other methods like _perform_tavily_search, _prioritize_pages, _calculate_name_match_in_url, etc., remain the same as the previous version) ...
    def _perform_tavily_search(self, first_name, last_name, company=None):
        """
        Perform a web search using Tavily API.
        Requires TAVILY_API_KEY in settings.
        """
        if not tavily_available or not TavilyClient:
             logger.error("TavilyClient not initialized.")
             return []

        api_key = getattr(settings, 'TAVILY_API_KEY', None)
        if not api_key:
            logger.error("TAVILY_API_KEY missing in settings.")
            return []

        try:
            # Construct search term - keep quotes for Tavily? Test this.
            search_term = f'"{first_name} {last_name}"'
            if company:
                search_term += f' "{company}"'
            # Keep site:linkedin.com/in/ for Tavily as it's likely more powerful
            search_term += ' site:linkedin.com/in/'

            logger.debug(f"Tavily Search Query: {search_term}")
            tavily = TavilyClient(api_key=api_key)
            response = tavily.search(
                 query=search_term,
                 search_depth="basic",
                 max_results=10,
                 include_raw_content=False,
                 include_answer=False
            )
            logger.debug(f"Tavily API Response: {response}")

            results = []
            result_items = response.get('results', [])
            for item in result_items:
                if isinstance(item, dict) and item.get('url') and 'linkedin.com/in/' in item.get('url'):
                     # Ensure Tavily results are also profile URLs if site: was used
                    results.append({
                        'title': item.get('title', ''),
                        'url': item.get('url'),
                        'snippet': item.get('content', ''),
                        'source': 'tavily'
                    })
                elif isinstance(item, dict) and item.get('url'):
                     logger.debug(f"Tavily returned non /in/ URL despite site: query: {item.get('url')}")


            return results

        except Exception as e:
            logger.error(f"Error performing Tavily search: {e}", exc_info=self.verbose)
            return []

    def _prioritize_pages(self, search_results, first_name, last_name, company=None):
        """
        Prioritize search result pages based on likelihood of containing the target LinkedIn profile.
        """
        prioritized = []
        num_results = len(search_results) # For rank bonus calculation

        for rank, result in enumerate(search_results):
            url = result['url']
            title = result.get('title', '')
            snippet = result.get('snippet', '')

            if not url or not isinstance(url, str): continue
            try: # Add basic robustness for URL parsing
                parsed_url = urlparse(url)
                if not parsed_url.scheme:
                    url = 'https://' + url
                    parsed_url = urlparse(url) # Re-parse after adding scheme
                if not parsed_url.netloc: # Skip if URL is fundamentally broken
                     logger.warning(f"Skipping invalid URL in prioritization: {url}")
                     continue
            except ValueError as url_err:
                 logger.warning(f"Skipping invalid URL due to parsing error: {url} ({url_err})")
                 continue

            # Optionally re-enable domain filtering if needed, but search query should handle it mostly
            # if 'linkedin.com' not in parsed_url.netloc.lower():
            #      logger.debug(f"Skipping non-LinkedIn URL from search results: {url}")
            #      continue

            priority = 0.0
            reason_parts = []
            content_lower = (title + ' ' + snippet).lower()
            first_lower = first_name.lower()
            last_lower = last_name.lower()
            company_lower = company.lower() if company else None

            # Base score
            if 'linkedin.com' in parsed_url.netloc.lower():
                 priority += 50
                 reason_parts.append("LinkedIn Domain")

            # Direct Profile URL Boost
            is_direct_profile = '/in/' in parsed_url.path
            if is_direct_profile:
                priority += 200
                reason_parts.append("Direct Profile URL")
                name_url_score = self._calculate_name_match_in_url(url, first_name, last_name)
                if name_url_score > 0:
                    priority += 75 * name_url_score
                    reason_parts.append(f"Name Match in URL ({name_url_score:.2f})")

            # Company association
            if company_lower:
                 if company_lower.replace(' ', '') in url.lower().replace('-', ''):
                      priority += 70
                      reason_parts.append("Company in URL")
                 if company_lower in content_lower:
                      priority += 100
                      reason_parts.append(f"Company in Content")

            # Name association in title/snippet
            name_in_content = first_lower in content_lower and last_lower in content_lower
            if name_in_content:
                priority += 30
                reason_parts.append("Full Name in Content")
            elif first_lower in content_lower or last_lower in content_lower:
                 priority += 10
                 reason_parts.append("Partial Name in Content")

            # Profile-related terms
            if any(term in content_lower for term in ['profile', 'résumé', 'professional', 'connect']):
                priority += 5
                reason_parts.append("Profile Terms")

            # Search rank bonus
            if num_results > 0:
                 rank_bonus = max(0, (num_results - rank) / num_results) * 5
                 priority += rank_bonus

            if priority > 0:
                prioritized.append({
                    'url': url,
                    'title': title,
                    'snippet': snippet,
                    'priority': priority,
                    'reason': ', '.join(reason_parts) if reason_parts else 'Base Score',
                    'source': result.get('source', 'unknown')
                })
            else:
                 logger.debug(f"Skipping result with zero priority: {url}")

        return sorted(prioritized, key=lambda x: x['priority'], reverse=True)


    def _calculate_name_match_in_url(self, url, first_name, last_name):
        handle = self._extract_handle_from_url(url)
        if not handle: return 0.0
        handle_lower = handle.lower()
        first_lower = first_name.lower()
        last_lower = last_name.lower()
        score = 0.0
        handle_alpha = ''.join(filter(str.isalpha, handle_lower))
        first_last_dash = f"{first_lower}-{last_lower}"
        last_first_dash = f"{last_lower}-{first_lower}"
        first_last_concat = f"{first_lower}{last_lower}"
        last_first_concat = f"{last_lower}{first_lower}"

        if handle_lower == first_last_dash: return 1.0
        if handle_lower == last_first_dash: return 0.95
        if handle_lower == first_last_concat or handle_lower == last_first_concat: return 0.9
        if f"{first_lower}-{last_lower[0]}" in handle_lower or f"{first_lower[0]}-{last_lower}" in handle_lower: score = max(score, 0.85)
        if f"{first_lower}.{last_lower}" in handle_lower or f"{first_lower}_{last_lower}" in handle_lower: score = max(score, 0.8)
        if score == 0 and first_lower in handle_lower and last_lower in handle_lower:
             if handle_alpha == first_last_concat or handle_alpha == last_first_concat: score = 0.75
             else: score = 0.65
        if score == 0 and (first_lower in handle_lower or last_lower in handle_lower): score = 0.4
        return score

    def _clean_profile_url(self, url):
         if not url or '/in/' not in url: return url
         try:
              base = url.split('/in/')[0] + '/in/'
              handle_part = url.split('/in/')[1]
              clean_handle = handle_part.split('?')[0].split('/')[0].rstrip('/')
              return base + clean_handle
         except IndexError: return url

    def _extract_handle_from_url(self, url):
        if not url or '/in/' not in url: return None
        try:
            after_in = url.split('/in/')[1]
            handle = after_in.split('?')[0].split('/')[0].rstrip('/')
            return handle
        except IndexError:
            logger.debug(f"Could not extract handle from URL: {url}")
            return None

    def _fetch_page(self, url):
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5','Referer': 'https://www.google.com/','DNT': '1','Upgrade-Insecure-Requests': '1'
        }
        try:
            response = requests.get(url, headers=headers, timeout=12, allow_redirects=True)
            response.raise_for_status()
            content_type = response.headers.get('content-type', '').lower()
            if 'html' not in content_type:
                logger.warning(f"Skipping non-HTML content at {url} (Content-Type: {content_type})")
                return None
            if "captcha" in response.text.lower() or "sign in" in response.text.lower():
                 logger.warning(f"Possible CAPTCHA or login page detected at {url}")
            return response.text
        except requests.exceptions.Timeout: logger.warning(f"Timeout fetching page {url}"); return None
        except requests.exceptions.TooManyRedirects: logger.warning(f"Too many redirects fetching page {url}"); return None
        except requests.exceptions.RequestException as e: logger.error(f"Error fetching page {url}: {e}"); return None
        except Exception as e: logger.error(f"Unexpected error fetching page {url}: {e}", exc_info=self.verbose); return None

    def _calculate_profile_match_score(self, url, context, first_name, last_name, company=None):
        score = 0.0
        url = self._clean_profile_url(url)
        name_url_score = self._calculate_name_match_in_url(url, first_name, last_name)
        score += name_url_score * 10.0
        context_lower = context.lower() if context else ""
        if context_lower:
            if first_name.lower() in context_lower: score += 3.0
            if last_name.lower() in context_lower: score += 3.0
        if company and context_lower and company.lower() in context_lower: score += 8.0
        return min(score, self.MAX_SCORE)

    def _extract_linkedin_profiles(self, page_content, first_name, last_name, company=None):
        soup = BeautifulSoup(page_content, 'html.parser')
        found_profiles = []
        links = soup.find_all('a', href=True)
        for link in links:
            href = link['href']
            parsed_href = urlparse(href)
            if 'linkedin.com' in parsed_href.netloc.lower() and '/in/' in parsed_href.path:
                clean_url = self._clean_profile_url(href)
                if not self._extract_handle_from_url(clean_url): continue
                link_text = link.get_text(strip=True)
                parent = link.parent; parent_text = ""; tries = 0
                while parent and tries < 3:
                     parent_text = parent.get_text(separator=' ', strip=True)
                     if len(parent_text) > 50: break
                     parent = parent.parent; tries += 1
                context = (link_text + ' ' + parent_text)[:500]
                match_score = self._calculate_profile_match_score(clean_url, context, first_name, last_name, company)
                if match_score > 0:
                    found_profiles.append({'url': clean_url, 'text': link_text, 'context': context, 'match': match_score})
        return found_profiles

    def _rank_profiles(self, profiles_list):
        if not profiles_list: return []
        for profile in profiles_list:
            confidence = min(1.0, profile.get('match', 0) / self.MAX_SCORE)
            profile['confidence'] = f"{int(confidence * 100)}%"
        ranked_profiles = sorted(
            profiles_list,
            key=lambda p: (p.get('match', 0), p.get('source_type') == 'direct_url', -len(p.get('url', ''))),
            reverse=True
        )
        logger.debug("--- Ranked Profiles ---")
        for i, p in enumerate(ranked_profiles[:5]):
             logger.debug(f"{i+1}. Score: {p.get('match', 0):.1f}, Conf: {p.get('confidence', 'N/A')}, Source: {p.get('source_type', 'N/A')}, URL: {p.get('url', 'N/A')}")
        logger.debug("---------------------")
        return ranked_profiles
    
    


##############################
## MAIN CONTROLLER CLASS ##
##############################
class EmployeeResearchController:
    """
    Controller for researching employees/contacts at companies using web search
    and direct LinkedIn profile fetching.
    """

    # Define company size thresholds
    SIZE_THRESHOLDS = {
        SIZE_SMALL: 50,
        SIZE_MEDIUM: 200,
        SIZE_LARGE: float('inf') # Represents > 200
    }

    # Define target keywords mapped to roles and influence
    # Keys are role names (for internal use), values are tuples:
    # (CompanyRole object, list_of_keywords, default_influence)
    TARGET_ROLES_BASE = {
        'executive': (None, ['CEO', 'Chief Executive Officer', 'Founder', 'CTO', 'Chief Technology Officer', 'CFO', 'Chief Financial Officer', 'COO', 'Chief Operating Officer', 'President'], 10),
        'recruiter': (None, ['Recruiter', 'Talent Acquisition', 'Sourcer', 'Human Resources', 'HR', 'People Operations', 'People Partner', 'Talent Partner'], 7),
        'hiring_manager': (None, ['Manager', 'Director', 'Head of', 'VP', 'Vice President', 'Lead'], 8),
        # Add more roles as needed
    }

    
    def __init__(self, company_profile: CompanyProfile, linkedin_api_client, job_id: int = None, verbose=False):
        """
        Initialize the controller.

        Args:
            company_profile: The CompanyProfile object to research.
            linkedin_api_client: An authenticated instance of the linkedin_api client.
            job_id: Optional ID of the specific job to provide context.
            verbose: Boolean for verbose logging output.
        """
        if not isinstance(company_profile, CompanyProfile):
            raise TypeError("company_profile must be an instance of CompanyProfile")
        if not linkedin_api_client:
             raise ValueError("linkedin_api_client is required")

        self.company = company_profile
        self.linkedin_api = linkedin_api_client # Use the passed-in authenticated client
        self.job = None
        self.verbose = verbose
        self.profile_finder = LinkedInProfileFinder(verbose=self.verbose) # For web searches

        if job_id:
            try:
                self.job = Job.objects.select_related('company_profile').get(id=job_id)
                # Ensure the job's company matches the controller's company
                if self.job.company_profile and self.job.company_profile.id != self.company.id:
                     logger.warning(f"Job {job_id}'s company ({self.job.company_profile.name}) differs from controller's company ({self.company.name}). Proceeding with controller's company.")
                elif not self.job.company_profile and self.job.company_name != self.company.name:
                     logger.warning(f"Job {job_id}'s company name ({self.job.company_name}) differs from controller's company ({self.company.name}). Proceeding with controller's company.")

            except Job.DoesNotExist:
                logger.warning(f"Job with ID {job_id} not found for context.")

        # Initialize CompanyRole objects lazily or here
        self._init_company_roles()
        # Update TARGET_ROLES_BASE with actual role objects
        for role_key, (role_obj, keywords, influence) in self.TARGET_ROLES_BASE.items():
             role_attr_name = f"{role_key}_role"
             if hasattr(self, role_attr_name):
                  self.TARGET_ROLES_BASE[role_key] = (getattr(self, role_attr_name), keywords, influence)

    
    def _init_company_roles(self):
        """Initialize company role objects, fetching or creating them."""
        # Fetch roles defined in TARGET_ROLES_BASE keys if specific roles are desired
        self.executive_role, _ = CompanyRole.objects.get_or_create(name="Executive", defaults={"description": "C-level or executive leadership."})
        self.recruiter_role, _ = CompanyRole.objects.get_or_create(name="Recruiter", defaults={"description": "Recruiter, Talent Acquisition, HR involved in hiring."})
        self.hiring_manager_role, _ = CompanyRole.objects.get_or_create(name="Hiring Manager", defaults={"description": "Manager, Director, VP, or Lead likely responsible for hiring."})
        # Add other roles if needed based on TARGET_ROLES_BASE or specific logic
        # self.engineering_lead_role, _ = CompanyRole.objects.get_or_create(...)

    def _get_company_size_category(self) -> str:
        """Determine company size category based on employee count."""
        count = self.company.employee_count_max or self.company.employee_count_min
        if count is None:
            logger.warning(f"Company size unknown for {self.company.name}. Defaulting to '{SIZE_MEDIUM}' strategy.")
            return SIZE_MEDIUM # Default strategy for unknown size

        if count <= self.SIZE_THRESHOLDS[SIZE_SMALL]:
            return SIZE_SMALL
        elif count <= self.SIZE_THRESHOLDS[SIZE_MEDIUM]:
            return SIZE_MEDIUM
        else:
            return SIZE_LARGE


    def _get_target_role_keywords(self, size_category: str) -> Dict[str, Tuple[CompanyRole, List[str], int]]:
        """Get the relevant role keywords and info based on company size."""
        targets = {}
        base_targets = self.TARGET_ROLES_BASE

        if size_category == SIZE_SMALL:
            targets['executive'] = base_targets['executive']
            targets['recruiter'] = base_targets['recruiter'] # HR/Recruiters exist in small companies too
            targets['hiring_manager'] = base_targets['hiring_manager']
        elif size_category == SIZE_MEDIUM:
            targets['recruiter'] = base_targets['recruiter']
            targets['hiring_manager'] = base_targets['hiring_manager']
            # Maybe add specific VPs if job context allows? (Future enhancement)
        elif size_category == SIZE_LARGE:
            targets['recruiter'] = base_targets['recruiter'] # Focus heavily here
            # Maybe refine hiring manager search (e.g., only Director+)?
            targets['hiring_manager'] = base_targets['hiring_manager']
        else: # Unknown size - take a mixed approach
             targets['recruiter'] = base_targets['recruiter']
             targets['hiring_manager'] = base_targets['hiring_manager']

        logger.info(f"Targeting roles for {size_category} company: {list(targets.keys())}")
        return targets
    


    def _search_for_role_profiles(self, role_keywords: List[str]) -> List[str]:
        """Perform web search to find LinkedIn profile URLs for given roles at the company."""
        found_urls = set()
        max_search_results_per_keyword = 5 # Limit search results per keyword

        for keyword in role_keywords:
            query = f'"{keyword}" "{self.company.name}" site:linkedin.com/in/'
            logger.info(f"Web searching for: {query}")
            try:
                 # Using the LinkedInProfileFinder's search method directly
                 # We need access to the raw search results list, not just the best profile
                 # Let's modify LinkedInProfileFinder slightly or use Tavily directly

                 # --- Option: Using Tavily directly (if available) ---
                 if tavily_available:
                     tavily_client = TavilyClient(api_key=settings.TAVILY_API_KEY)
                     search_response = tavily_client.search(query=query, search_depth="basic", max_results=max_search_results_per_keyword)
                     search_results = search_response.get('results', [])
                 else:
                 # --- Option: Modify LinkedInProfileFinder._perform_duckduckgo_search (or add a new method) ---
                 # This requires adjusting LinkedInProfileFinder to return the raw list
                 # For now, let's assume Tavily or skip this keyword if no search tool
                     logger.warning("No search tool available (Tavily needed). Skipping web search for keyword.")
                     search_results = []


                 for result in search_results:
                     url = result.get('url')
                     if url and 'linkedin.com/in/' in url:
                         clean_url = self.profile_finder._clean_profile_url(url) # Use helper
                         if clean_url:
                             found_urls.add(clean_url)

                 # Add a small delay between keyword searches
                 time.sleep(random.uniform(0.5, 1.5))

            except Exception as e:
                logger.error(f"Error during web search for keyword '{keyword}': {e}", exc_info=self.verbose)

        logger.info(f"Found {len(found_urls)} potential unique profile URLs for roles: {role_keywords}")
        return list(found_urls)



    def _fetch_linkedin_profile(self, profile_url: str) -> Optional[Dict]:
        """Fetch structured data for a given LinkedIn profile URL using linkedin-api."""
        if not profile_url:
            return None
        logger.debug(f"Fetching profile details for: {profile_url}")
        try:
            # Extract public ID or URN if needed by get_profile
            profile_id = self.profile_finder._extract_handle_from_url(profile_url) # Or extract URN if possible/needed
            if not profile_id:
                 logger.warning(f"Could not extract profile ID from URL: {profile_url}")
                 return None

            # Call the authenticated API client's get_profile method
            # NOTE: Ensure get_profile accepts the public ID/handle. Some versions might require the URN.
            # Check the library's implementation.
            profile_data = self.linkedin_api.get_profile(profile_id) # Or get_profile(urn=...)

            if not profile_data:
                 logger.warning(f"No profile data returned for ID: {profile_id}")
                 return None

            # Add the URL back for reference, as get_profile might not return it
            profile_data['linkedin_profile_url'] = profile_url
            return profile_data

        except Exception as e:
            # Handle common errors like profile not found, rate limits, etc.
            logger.error(f"Error fetching profile {profile_url}: {e}", exc_info=False) # Keep log concise
            return None


    def _validate_profile_against_target(self, profile_data: Dict, target_keywords: List[str]) -> Optional[Dict]:
        """Validate fetched profile data against the company and target role keywords."""
        if not profile_data:
            return None

        current_experience = profile_data.get('experience', [])
        if not current_experience:
            logger.debug(f"Profile {profile_data.get('linkedin_profile_url')} has no 'experience' section. Skipping.")
            return None

        # --- 1. Validate Company Name ---
        # Get the company name from the *most recent* experience entry
        latest_experience = current_experience[0] # Assuming list is ordered chronologically
        profile_company_name = latest_experience.get('companyName')

        if not profile_company_name:
             logger.debug(f"Profile {profile_data.get('linkedin_profile_url')} latest experience has no company name. Skipping.")
             return None

        # Compare profile company name with target company name
        target_company_name = self.company.name
        match_ratio = 0
        if thefuzz_available:
            # Use fuzzy matching (adjust ratio threshold as needed)
            match_ratio = fuzz.token_set_ratio(target_company_name.lower(), profile_company_name.lower())
            company_match = match_ratio > 80 # Example threshold
        else:
            # Exact match (case-insensitive) if fuzzy matching not available
             company_match = target_company_name.lower() == profile_company_name.lower()

        if not company_match:
            logger.info(f"Profile company '{profile_company_name}' does not sufficiently match target '{target_company_name}' (Ratio: {match_ratio}). Skipping {profile_data.get('linkedin_profile_url')}.")
            return None
        else:
             logger.debug(f"Company name match successful for {profile_data.get('linkedin_profile_url')} (Ratio: {match_ratio})")


        # --- 2. Validate Job Title ---
        profile_job_title = latest_experience.get('title')
        if not profile_job_title:
            logger.debug(f"Profile {profile_data.get('linkedin_profile_url')} latest experience has no job title. Skipping.")
            return None

        title_lower = profile_job_title.lower()
        title_match = any(keyword.lower() in title_lower for keyword in target_keywords)

        if not title_match:
            logger.info(f"Profile title '{profile_job_title}' does not contain target keywords {target_keywords}. Skipping {profile_data.get('linkedin_profile_url')}.")
            return None
        else:
             logger.debug(f"Job title match successful for {profile_data.get('linkedin_profile_url')}")


        # --- 3. Extract Basic Info ---
        first_name = profile_data.get('firstName')
        last_name = profile_data.get('lastName')
        linkedin_urn = profile_data.get('entityUrn') # Often looks like 'urn:li:profile:...'
        public_id = profile_data.get('publicIdentifier') # The part used in the URL

        if not first_name or not last_name:
             logger.warning(f"Profile {profile_data.get('linkedin_profile_url')} missing first or last name. Skipping.")
             return None

        # --- If all checks pass, return structured data ---
        validated_data = {
            "first_name": first_name,
            "last_name": last_name,
            "job_title": profile_job_title, # Use the title from the profile
            "company_name": profile_company_name, # Use the company name from the profile
            "linkedin_url": profile_data.get('linkedin_profile_url'), # The URL we used to fetch
            "linkedin_urn": linkedin_urn,
            "linkedin_public_id": public_id,
            "profile_summary": profile_data.get('summary', ''), # Optional
        }
        return validated_data

    
    # --- Main Execution Method ---
    def find_company_employees(self) -> List[User]:
        """Main method to find and process employees."""
        start_time = timezone.now()
        logger.info(f"Starting employee research for company: {self.company.name} (ID: {self.company.id})")

        size_category = self._get_company_size_category()
        target_roles_info = self._get_target_role_keywords(size_category)

        all_potential_urls = set()
        structured_employee_data = [] # Store validated data before creating users

        # Search for each target role type
        for role_key, (role_obj, keywords, influence) in target_roles_info.items():
            logger.info(f"Searching for role type: {role_key} (Keywords: {keywords})")
            profile_urls = self._search_for_role_profiles(keywords)
            all_potential_urls.update(profile_urls)

        if not all_potential_urls:
            logger.warning("No potential LinkedIn profile URLs found via web search.")
            return []

        logger.info(f"Found {len(all_potential_urls)} unique potential profile URLs to investigate.")

        processed_urls = 0
        # Fetch and validate profiles
        for profile_url in all_potential_urls:
            # Optional: Add delay between profile fetches
            time.sleep(random.uniform(1.0, 3.0))

            profile_data = self._fetch_linkedin_profile(profile_url)
            processed_urls += 1

            if profile_data:
                # Validate against the company and *any* of the keywords we searched for initially
                # (A recruiter search might yield a VP of Talent, which is still relevant)
                all_target_keywords = [kw for _, keywords, _ in target_roles_info.values() for kw in keywords]
                validated_data = self._validate_profile_against_target(profile_data, all_target_keywords)

                if validated_data:
                    # Map the validated title to a specific role and influence
                    mapped_role, influence_score = self._map_title_to_company_role(validated_data['job_title'])
                    validated_data['mapped_role'] = mapped_role
                    validated_data['influence_score'] = influence_score
                    validated_data['source'] = f"linkedin_profile_fetch" # Mark source
                    structured_employee_data.append(validated_data)
                    logger.info(f"Validated contact: {validated_data['first_name']} {validated_data['last_name']} ({validated_data['job_title']})")


            if processed_urls % 10 == 0:
                 logger.info(f"Processed {processed_urls}/{len(all_potential_urls)} profile URLs...")

        if not structured_employee_data:
             logger.warning(f"No validated employee profiles found for {self.company.name}.")
             return []

        logger.info(f"Found {len(structured_employee_data)} validated contacts. Proceeding to create/update database records.")

        # Deduplicate and Create/Update Users and Associations
        user_objects = self._create_or_update_users(structured_employee_data)

        end_time = timezone.now()
        duration = (end_time - start_time).total_seconds()
        logger.info(f"Employee research for {self.company.name} completed in {duration:.2f} seconds. Created/Updated {len(user_objects)} user records.")

        return user_objects
    
    def _create_or_update_users(self, employee_data_list: List[Dict]) -> List[User]:
        """
        Create or update User and UserCompanyAssociation objects from structured data.
        Uses LinkedIn URL or URN as a primary key for finding users if available.
        """
        user_objects = []
        processed_count = 0
        created_users = 0
        updated_users = 0
        created_assocs = 0
        updated_assocs = 0

        # Deduplicate based on LinkedIn identifier first, then name
        unique_employees = self._deduplicate_employees(employee_data_list)
        logger.info(f"Processing {len(unique_employees)} unique potential employees after deduplication.")


        for employee_data in unique_employees:
            processed_count += 1
            first_name = employee_data.get("first_name", "").strip()
            last_name = employee_data.get("last_name", "").strip()
            linkedin_url = employee_data.get("linkedin_url")
            # Linkedin URN might be more stable if available: urn:li:profile:xxxx
            linkedin_urn = employee_data.get("linkedin_urn")
            job_title = employee_data.get("job_title")
            mapped_role = employee_data.get("mapped_role")
            influence = employee_data.get("influence_score", 5)
            source_note = f"Discovered via {employee_data.get('source', 'linkedin_research')}"

            if not first_name or not last_name:
                logger.warning(f"Skipping employee data due to missing name: {employee_data}")
                continue

            user = None
            user_found = False
            user_created = False

            # --- Find Existing User ---
            # 1. Try finding by LinkedIn URL via UserContactMethod or UserSourceLink
            if linkedin_url:
                 contact_method = UserContactMethod.objects.filter(
                      method_type__name="LinkedIn Profile", # Assumes this ContactMethodType exists
                      value=linkedin_url
                 ).select_related('user').first()
                 if contact_method:
                     user = contact_method.user
                     user_found = True
                     logger.debug(f"Found existing user {user.id} via LinkedIn URL in ContactMethod: {linkedin_url}")
                 else:
                      # Try UserSourceLink as well
                      source_link = UserSourceLink.objects.filter(
                           source_type="linkedin",
                           url=linkedin_url
                      ).select_related('user').first()
                      if source_link:
                           user = source_link.user
                           user_found = True
                           logger.debug(f"Found existing user {user.id} via LinkedIn URL in SourceLink: {linkedin_url}")

            # 2. If not found by URL, try finding by name (less reliable)
            # Consider adding company context here if users can have same name at different companies
            if not user_found:
                # This is prone to errors if names are common. Email would be better.
                # For now, let's skip name-based finding if URL wasn't found,
                # and rely on creating a new user with a placeholder email.
                # Or, generate a *more unique* placeholder based on URN/URL if possible.
                pass

            # --- Create or Update User ---
            if user_found:
                # Update existing user if needed
                update_fields = []
                if not user.first_name and first_name:
                    user.first_name = first_name
                    update_fields.append('first_name')
                if not user.last_name and last_name:
                    user.last_name = last_name
                    update_fields.append('last_name')
                # Update linkedin_handle if empty or different (using publicIdentifier if available)
                new_handle = employee_data.get('linkedin_public_id') or self.profile_finder._extract_handle_from_url(linkedin_url)
                if new_handle and user.linkedin_handle != new_handle:
                     user.linkedin_handle = new_handle
                     update_fields.append('linkedin_handle')

                if update_fields:
                    user.save(update_fields=update_fields)
                    updated_users += 1
                    logger.info(f"Updated existing User: {user.email} (ID: {user.id})")

            else:
                # Create new user with placeholder email
                placeholder_email = self._generate_placeholder_email(first_name, last_name, self.company.name, linkedin_urn or linkedin_url)
                try:
                    user = User.objects.create(
                        email=placeholder_email,
                        first_name=first_name,
                        last_name=last_name,
                        linkedin_handle = employee_data.get('linkedin_public_id') or self.profile_finder._extract_handle_from_url(linkedin_url)
                    )
                    user_created = True
                    created_users += 1
                    logger.info(f"Created new User: {user.email} (ID: {user.id})")
                except Exception as create_err: # Catch potential IntegrityError if email exists
                     logger.error(f"Failed to create user for {first_name} {last_name} with email {placeholder_email}: {create_err}")
                     # Attempt to fetch user by email if creation failed due to constraint
                     user = User.objects.filter(email=placeholder_email).first()
                     if not user: continue # Skip if still can't get user


            # --- Create/Update LinkedIn Contact Method and Source Link ---
            if user and linkedin_url:
                 try:
                      linkedin_method_type, _ = ContactMethodType.objects.get_or_create(
                           name="LinkedIn Profile", defaults={"category": "social"}
                      )
                      UserContactMethod.objects.update_or_create(
                           user=user, method_type=linkedin_method_type,
                           defaults={"value": linkedin_url}
                      )
                      UserSourceLink.objects.update_or_create(
                           user=user, url=linkedin_url, source_type="linkedin",
                           defaults={
                                "title": f"LinkedIn Profile: {user.first_name} {user.last_name}",
                                "notes": source_note
                           }
                      )
                 except Exception as link_err:
                      logger.error(f"Error creating/updating contact/source link for user {user.id}: {link_err}")


            # --- Create or Update Company Association ---
            if user:
                try:
                    association, assoc_created = UserCompanyAssociation.objects.update_or_create(
                        user=user,
                        company=self.company,
                        # Add job_title to key if you want unique entry per title at same company
                        # unique_together = ('user', 'company', 'job_title') in Meta
                        defaults={
                            "job_title": job_title,
                            # "department": employee_data.get("department"), # Add if available
                            "role": mapped_role, # Use the mapped role
                            "influence_level": influence,
                            "notes": source_note,
                            "relationship_status": "to_contact" # Default status
                        }
                    )
                    if assoc_created:
                        created_assocs += 1
                        logger.debug(f"Created UserCompanyAssociation for User {user.id} at Company {self.company.id}")
                    else:
                        updated_assocs += 1
                        logger.debug(f"Updated UserCompanyAssociation for User {user.id} at Company {self.company.id}")

                    user_objects.append(user)
                except Exception as assoc_err:
                     logger.error(f"Failed to create/update association for user {user.id} and company {self.company.id}: {assoc_err}")

        logger.info(f"User processing summary: Found={processed_count}, Users Created={created_users}, Users Updated={updated_users}, Assocs Created={created_assocs}, Assocs Updated={updated_assocs}")
        return user_objects
    

    def _deduplicate_employees(self, employees: List[Dict]) -> List[Dict]:
        """Deduplicate employee data based on LinkedIn URL/URN first, then name."""
        unique_employees_map = {}

        for emp in employees:
            key = None
            # Prioritize LinkedIn identifiers for uniqueness
            if emp.get('linkedin_urn'):
                key = emp['linkedin_urn']
            elif emp.get('linkedin_url'):
                # Normalize URL slightly for better matching
                key = self.profile_finder._clean_profile_url(emp['linkedin_url'])

            # If no LinkedIn ID, use name as fallback key (less reliable)
            if not key:
                 first_name = emp.get("first_name", "").strip().lower()
                 last_name = emp.get("last_name", "").strip().lower()
                 if first_name and last_name:
                      key = f"name::{first_name}|{last_name}"

            if not key: continue # Skip if no usable key

            if key in unique_employees_map:
                # Merge: Keep the most complete record, prioritize certain fields
                existing = unique_employees_map[key]
                for field in ['job_title', 'linkedin_url', 'linkedin_urn', 'linkedin_public_id', 'profile_summary']:
                     if not existing.get(field) and emp.get(field):
                         existing[field] = emp.get(field)

                # Take the higher influence score and corresponding role
                if emp.get('influence_score', 0) > existing.get('influence_score', 0):
                    existing['influence_score'] = emp.get('influence_score')
                    existing['mapped_role'] = emp.get('mapped_role') # Role linked to higher influence

                # Append sources if different? Or just keep one source note?
                # existing['source'] = existing.get('source', '') + "; " + emp.get('source', '')
            else:
                # Add new entry, ensure names are capitalized
                new_entry = emp.copy()
                new_entry["first_name"] = new_entry.get("first_name", "").strip().capitalize()
                new_entry["last_name"] = new_entry.get("last_name", "").strip().capitalize()
                unique_employees_map[key] = new_entry

        return list(unique_employees_map.values())
    
    def _deduplicate_employees(self, employees: List[Dict]) -> List[Dict]:
        """Deduplicate employee data based on LinkedIn URL/URN first, then name."""
        unique_employees_map = {}

        for emp in employees:
            key = None
            # Prioritize LinkedIn identifiers for uniqueness
            if emp.get('linkedin_urn'):
                key = emp['linkedin_urn']
            elif emp.get('linkedin_url'):
                # Normalize URL slightly for better matching
                key = self.profile_finder._clean_profile_url(emp['linkedin_url'])

            # If no LinkedIn ID, use name as fallback key (less reliable)
            if not key:
                 first_name = emp.get("first_name", "").strip().lower()
                 last_name = emp.get("last_name", "").strip().lower()
                 if first_name and last_name:
                      key = f"name::{first_name}|{last_name}"

            if not key: continue # Skip if no usable key

            if key in unique_employees_map:
                # Merge: Keep the most complete record, prioritize certain fields
                existing = unique_employees_map[key]
                for field in ['job_title', 'linkedin_url', 'linkedin_urn', 'linkedin_public_id', 'profile_summary']:
                     if not existing.get(field) and emp.get(field):
                         existing[field] = emp.get(field)

                # Take the higher influence score and corresponding role
                if emp.get('influence_score', 0) > existing.get('influence_score', 0):
                    existing['influence_score'] = emp.get('influence_score')
                    existing['mapped_role'] = emp.get('mapped_role') # Role linked to higher influence

                # Append sources if different? Or just keep one source note?
                # existing['source'] = existing.get('source', '') + "; " + emp.get('source', '')
            else:
                # Add new entry, ensure names are capitalized
                new_entry = emp.copy()
                new_entry["first_name"] = new_entry.get("first_name", "").strip().capitalize()
                new_entry["last_name"] = new_entry.get("last_name", "").strip().capitalize()
                unique_employees_map[key] = new_entry

        return list(unique_employees_map.values())


    def _generate_placeholder_email(self, first_name: str, last_name: str, company_name: str, identifier: Optional[str] = None) -> str:
        """Generate a placeholder email, trying to make it unique."""
        first = re.sub(r'\W+', '', first_name).lower()
        last = re.sub(r'\W+', '', last_name).lower()
        comp = re.sub(r'\W+', '', company_name).lower()[:15] # Limit company part length

        unique_part = ""
        if identifier: # Use part of URN or URL hash for uniqueness
            if "urn:li:profile:" in identifier:
                unique_part = identifier.split(':')[-1][:8] # Use first 8 chars of ID part
            elif "linkedin.com/in/" in identifier:
                 handle = self.profile_finder._extract_handle_from_url(identifier)
                 if handle: unique_part = handle[:8]

        if unique_part:
             return f"{first}.{last}.{unique_part}@{comp}.fartemis.placeholder"
        else:
             # Fallback if no identifier - less unique
             timestamp = str(int(time.time() * 1000))[-6:] # Add timestamp part
             return f"{first}.{last}.{timestamp}@{comp}.fartemis.placeholder"