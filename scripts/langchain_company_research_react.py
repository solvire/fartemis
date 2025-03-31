#!/usr/bin/env python
# -*- coding: utf-8 -*-
# make sure to export your keys
# export TAVILY_API_KEY=your_api_key 
# export ANTHROPIC_API_KEY=your_api_key

import getpass
import os
from langchain_tavily import TavilySearch
from langchain.chat_models import init_chat_model
from langchain_tavily import TavilySearch
from langgraph.prebuilt import create_react_agent

if not os.environ.get("TAVILY_API_KEY"):
    os.environ["TAVILY_API_KEY"] = getpass.getpass("Tavily API key:\n")

if not os.environ.get("ANTHROPIC_API_KEY"):
  os.environ["ANTHROPIC_API_KEY"] = getpass.getpass("Enter API key for Anthropic: ")


llm = init_chat_model("claude-3-7-sonnet-latest", model_provider="anthropic")

query = """
I need a company profile on Epic Games in Raleigh, NC. 
You are going to help me understand the type of company and culture as if I am evaluating working for that organization.
"""

# tool = TavilySearch(
#     max_results=5,
#     topic="general",
#     include_answer=True,
#     # include_raw_content=True,
#     # include_images=False,
#     # include_image_descriptions=False,
#     search_depth="advanced",
#     # time_range="day",
#     # include_domains=None,
#     # exclude_domains=None
# )
# results = tool.invoke({"query": query})
# print(results)


## agent re/act

tavily_search_tool = TavilySearch(
    max_results=10,
    topic="general",
    search_depth="advanced",
)

agent = create_react_agent(llm, [tavily_search_tool])


for step in agent.stream(
    {"messages": query},
    stream_mode="values",
):
    step["messages"][-1].pretty_print()