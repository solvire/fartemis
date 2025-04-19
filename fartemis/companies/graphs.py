from langchain_core.prompts import ChatPromptTemplate
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph
import json

def create_company_sentiment_graph():
    """
    Creates a LangGraph workflow for researching company sentiment
    """
    # Define the state
    class GraphState:
        """State for the company research workflow"""
        company: dict  # Company profile data
        queries: list  # Generated search queries
        search_results: list  # Results from Tavily
        references: list  # Processed references
        sentiment_analysis: dict  # Extracted sentiment
    
    # Initialize the graph
    workflow = StateGraph(GraphState)
    
    # Node 1: Generate search queries based on company info
    query_gen_prompt = ChatPromptTemplate.from_template(
        """You are researching the company {company_name}. 
        Generate 3 specific search queries to find information about this company's:
        1. Employee sentiment and workplace culture
        2. Industry reputation and customer reviews
        3. Recent company news and developments
        
        FORMAT: Return just a list of 3 queries as a JSON array."""
    )
    
    # Connect to LLM
    llm = ChatOpenAI(temperature=0)
    
    # Create the query generator node
    query_generator = (
        query_gen_prompt 
        | llm 
        | StrOutputParser() 
        | (lambda x: {"queries": json.loads(x)})
    )
    
    # Node 2: Search using Tavily
    def search_tavily(state):
        """Execute Tavily searches for all queries"""
        search_tool = TavilySearchResults(max_results=5, k=5)
        results = []
        
        for query in state.queries:
            query_results = search_tool.invoke(query)
            for result in query_results:
                result["original_query"] = query
            results.extend(query_results)
            
        return {"search_results": results}
    
    # Node 3: Process references
    def process_references(state):
        """Transform search results into structured references"""
        references = []
        
        for result in state.search_results:
            reference = {
                "title": result["title"],
                "url": result["url"],
                "content": result.get("content", ""),
                "original_query": result["original_query"],
                "score": result.get("score", 0)
            }
            references.append(reference)
            
        return {"references": references}
    
    # Node 4: Analyze sentiment
    sentiment_prompt = ChatPromptTemplate.from_template(
        """Analyze the sentiment regarding {company_name} from the following search results:
        
        {references}
        
        Provide a structured analysis in the following JSON format:
        {
            "overall_sentiment": "positive/negative/neutral/mixed",
            "overall_score": (float between 0-10, with 10 being most positive),
            "key_themes": ["theme1", "theme2", ...],
            "summary": "brief summary of sentiment findings",
            "reference_sentiments": [{
                "url": "reference URL",
                "sentiment": "positive/negative/neutral/mixed",
                "score": (float between 0-10),
                "key_quotes": ["quote1", "quote2"]
            }]
        }"""
    )
    
    sentiment_analyzer = (
        sentiment_prompt 
        | llm 
        | StrOutputParser() 
        | (lambda x: {"sentiment_analysis": json.loads(x)})
    )
    
    # Add nodes to the graph
    workflow.add_node("generate_queries", query_generator)
    workflow.add_node("search_tavily", search_tavily)
    workflow.add_node("process_references", process_references)
    workflow.add_node("analyze_sentiment", sentiment_analyzer)
    
    # Define edges
    workflow.add_edge("generate_queries", "search_tavily")
    workflow.add_edge("search_tavily", "process_references")
    workflow.add_edge("process_references", "analyze_sentiment")
    
    # Set the entry point
    workflow.set_entry_point("generate_queries")
    
    return workflow.compile()