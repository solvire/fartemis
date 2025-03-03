# fartemis/llm/clients.py
"""
Clients for interacting with large language models
@author: solvire
@date: 2025-03-02
"""
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Union

import anthropic

from fartemis.llm.constants import LLMProvider, ModelName

logger = logging.getLogger(__name__)


class BaseLLMClient(ABC):
    """
    Abstract base class for LLM clients
    """
    
    def __init__(self, **kwargs):
        self.api_key = kwargs.get('api_key')
        self.model = kwargs.get('model')
        self.default_params = kwargs.get('default_params', {})
        
    @abstractmethod
    def complete(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Generate text completion
        
        Args:
            prompt (str): The prompt to complete
            **kwargs: Additional parameters to pass to the provider
            
        Returns:
            Dict[str, Any]: Response containing the completion and metadata
        """
        pass
    
    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        """
        Generate chat completion from a list of messages
        
        Args:
            messages (List[Dict[str, str]]): List of message dictionaries with role and content
            **kwargs: Additional parameters to pass to the provider
            
        Returns:
            Dict[str, Any]: Response containing the completion and metadata
        """
        pass
    
    @abstractmethod
    def embeddings(self, text: Union[str, List[str]], **kwargs) -> Dict[str, Any]:
        """
        Generate embeddings for text
        
        Args:
            text (Union[str, List[str]]): Text or list of texts to embed
            **kwargs: Additional parameters to pass to the provider
            
        Returns:
            Dict[str, Any]: Response containing the embeddings and metadata
        """
        pass
    
    @abstractmethod
    def function_call(self, messages: List[Dict[str, str]], functions: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
        """
        Generate function calls based on messages
        
        Args:
            messages (List[Dict[str, str]]): List of message dictionaries
            functions (List[Dict[str, Any]]): List of function definitions
            **kwargs: Additional parameters to pass to the provider
            
        Returns:
            Dict[str, Any]: Response containing the function call and metadata
        """
        pass
    
    def render_prompt(self, template: str, **kwargs) -> str:
        """
        Render a prompt template with variables
        
        Args:
            template (str): The prompt template with {variable} placeholders
            **kwargs: Values to fill in the template
            
        Returns:
            str: The rendered prompt
        """
        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.error(f"Missing variable in prompt template: {e}")
            raise ValueError(f"Missing variable in prompt template: {e}")


class AnthropicClient(BaseLLMClient):
    """
    Client for Anthropic's Claude models
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.client = anthropic.Anthropic(api_key=self.api_key)
        
    def complete(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Generate text completion using the Messages API
        """
        params = self.default_params.copy()
        params.update(kwargs)
        
        try:
            # Convert the single prompt to a messages format
            messages = [{"role": "user", "content": prompt}]
            
            response = self.client.messages.create(
                model=self.model,
                messages=messages,
                **params
            )
            
            # Extract the text from the response
            text = ""
            if response.content and len(response.content) > 0:
                if hasattr(response.content[0], 'text'):
                    text = response.content[0].text
                
            return {
                'text': text,
                'model': response.model,
                'raw_response': response
            }
        except Exception as e:
            logger.error(f"Error in Anthropic completion: {e}")
            raise
    
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        params = self.default_params.copy()
        params.update(kwargs)
        
        # Convert messages to Anthropic format if needed
        anthropic_messages = []
        system_message = None
        
        for msg in messages:
            role = msg['role'].lower()
            if role == 'user':
                anthropic_messages.append({"role": "user", "content": msg['content']})
            elif role == 'assistant':
                anthropic_messages.append({"role": "assistant", "content": msg['content']})
            elif role == 'system':
                system_message = msg['content']
        
        try:
            # Add system message if present
            if system_message:
                params['system'] = system_message
                
            response = self.client.messages.create(
                model=self.model,
                messages=anthropic_messages,
                **params
            )
            
            # Extract the text from the response
            text = ""
            if response.content and len(response.content) > 0:
                if hasattr(response.content[0], 'text'):
                    text = response.content[0].text
                
            return {
                'text': text,
                'model': response.model,
                'raw_response': response
            }
        except Exception as e:
            logger.error(f"Error in Anthropic chat: {e}")
            raise
    
    def embeddings(self, text: Union[str, List[str]], **kwargs) -> Dict[str, Any]:
        # As of my knowledge cutoff, Anthropic doesn't have a public embeddings API
        # This would need to be updated when they release one
        raise NotImplementedError("Anthropic embeddings not implemented yet")
    
    def function_call(self, messages: List[Dict[str, str]], functions: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
        params = self.default_params.copy()
        params.update(kwargs)
        
        # Convert functions to Anthropic's tools format
        tools = [{"type": "function", "function": func} for func in functions]
        
        try:
            response = self.client.messages.create(
                model=self.model,
                messages=messages,
                tools=tools,
                **params
            )
            
            # Extract function call from response
            tool_calls = []
            for content in response.content:
                if content.type == "tool_use":
                    tool_calls.append({
                        "name": content.tool_use.name,
                        "arguments": content.tool_use.parameters
                    })
            
            return {
                'text': response.content[0].text if response.content[0].type == "text" else "",
                'tool_calls': tool_calls,
                'model': response.model,
                'raw_response': response
            }
        except Exception as e:
            logger.error(f"Error in Anthropic function call: {e}")
            raise


class LLMClientFactory:
    """
    Factory for creating LLM clients
    """
    
    @staticmethod
    def create(provider: str, api_key: str, model: str = None, **kwargs) -> BaseLLMClient:
        """
        Create an LLM client for the specified provider
        
        Args:
            provider (str): Provider name from LLMProvider constants
            api_key (str): API key for the provider
            model (str, optional): Model name to use
            **kwargs: Additional parameters for the client
            
        Returns:
            BaseLLMClient: An initialized LLM client
        """
        if provider == LLMProvider.ANTHROPIC:
            model = model or ModelName.CLAUDE_3_SONNET
            return AnthropicClient(api_key=api_key, model=model, **kwargs)
        elif provider == LLMProvider.OPENAI:
            model = model or ModelName.GPT_4_TURBO
            return OpenAIClient(api_key=api_key, model=model, **kwargs)
        elif provider == LLMProvider.MISTRAL:
            model = model or ModelName.MISTRAL_LARGE
            return MistralClient(api_key=api_key, model=model, **kwargs)
        elif provider == LLMProvider.GOOGLE:
            model = model or ModelName.GEMINI_PRO
            return GoogleClient(api_key=api_key, model=model, **kwargs)
        elif provider == LLMProvider.OLLAMA:
            model = model or ModelName.LLAMA_3
            return OllamaClient(api_key=api_key, model=model, **kwargs)
        else:
            raise ValueError(f"Unsupported provider: {provider}")
