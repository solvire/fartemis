# fartemis/llm/clients.py
"""
Clients for interacting with large language models
@author: solvire
@date: 2025-03-02
"""

import logging
import os
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Union

import anthropic
import deepl
from django.conf import settings

from fartemis.llms.constants import LLMProvider, ModelName

logger = logging.getLogger(__name__)


class BaseLLMClient(ABC):
    """
    Abstract base class for LLM clients
    """
    
    def __init__(self, **kwargs):
        self.provider = kwargs.get('provider')
        self.model = kwargs.get('model')
        self.default_params = kwargs.get('default_params', {})

    def get_model(self):
        return self.model
        
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
        self.provider = LLMProvider.ANTHROPIC
        api_key = kwargs.get('api_key') or self._get_api_key()
        self.client = anthropic.Anthropic(api_key=api_key)
        
    def _get_api_key(self):
        """Get API key from settings"""
        return getattr(settings, 'ANTHROPIC_API_KEY', None)
        
    def complete(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Generate text completion using the Messages API
        """
        params = self.default_params.copy()
        params.update(kwargs)
        
        try:
            # Convert the single prompt to a messages format
            messages = [{"role": "user", "content": prompt}]
            
            # Ensure max_tokens is set
            if "max_tokens" not in params:
                params["max_tokens"] = 1000  # Default value
            
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

        # Ensure max_tokens is set
        if "max_tokens" not in params:
            params["max_tokens"] = 1000  # Default value
        
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

        # Ensure max_tokens is set
        if "max_tokens" not in params:
            params["max_tokens"] = 1000  # Default value
        
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


class DeepseekClient(BaseLLMClient):
    """
    Client for Deepseek models
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.provider = LLMProvider.DEEPSEEK
        
        # Get API key from settings if not provided
        api_key = kwargs.get('api_key') or self._get_api_key()
        
        # Import Deepseek client here to avoid import errors if the package is not installed
        try:
            # Using the LangChain implementation for simplicity
            from langchain_deepseek import ChatDeepSeek
            self.client = ChatDeepSeek(
                model=self.model,
                api_key=api_key,
                temperature=kwargs.get('default_params', {}).get('temperature', 0.7)
            )
        except ImportError:
            logger.error("langchain_deepseek package not installed")
            raise ImportError("Please install the langchain_deepseek package to use Deepseek")
    
    def _get_api_key(self):
        """Get API key from settings"""
        return getattr(settings, 'DEEPSEEK_API_KEY', None)
    
    def complete(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Generate text completion
        """
        params = self.default_params.copy()
        params.update(kwargs)
        
        try:
            # Adapt to LangChain interface
            response = self.client.invoke(prompt)
            
            return {
                'text': response.content,
                'model': self.model,
                'raw_response': response
            }
        except Exception as e:
            logger.error(f"Error in Deepseek completion: {e}")
            raise
    
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        """
        Generate chat completion
        """
        params = self.default_params.copy()
        params.update(kwargs)
        
        try:
            # Convert to LangChain message format
            from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
            
            langchain_messages = []
            for msg in messages:
                role = msg['role'].lower()
                content = msg['content']
                
                if role == 'user':
                    langchain_messages.append(HumanMessage(content=content))
                elif role == 'assistant':
                    langchain_messages.append(AIMessage(content=content))
                elif role == 'system':
                    langchain_messages.append(SystemMessage(content=content))
            
            response = self.client.invoke(langchain_messages)
            
            return {
                'text': response.content,
                'model': self.model,
                'raw_response': response
            }
        except Exception as e:
            logger.error(f"Error in Deepseek chat: {e}")
            raise
    
    def embeddings(self, text: Union[str, List[str]], **kwargs) -> Dict[str, Any]:
        """
        Generate embeddings for text
        """
        raise NotImplementedError("Deepseek embeddings not implemented yet")
    
    def function_call(self, messages: List[Dict[str, str]], functions: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
        """
        Generate function calls
        """
        raise NotImplementedError("Deepseek function calling not implemented yet")


class DeepLClient(BaseLLMClient):
    """
    Client for DeepL translation service
    This is NOT an LLM but a translation service
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.provider = LLMProvider.DEEPL
        api_key = kwargs.get('api_key') or self._get_api_key()
        
        # Initialize the DeepL translator
        try:
            self.client = deepl.Translator(api_key)
        except Exception as e:
            logger.error(f"Error initializing DeepL translator: {e}")
            raise
    
    def _get_api_key(self):
        """Get API key from settings"""
        return getattr(settings, 'DEEPL_API_KEY', None)
    
    def complete(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Translate text using DeepL API
        
        Args:
            prompt (str): The text to translate
            **kwargs: Additional parameters including:
                - target_lang: Target language code (e.g., 'EN', 'DE', 'FR')
                - source_lang: Source language code (optional)
        """
        params = self.default_params.copy()
        params.update(kwargs)
        
        # Get target language, defaulting to English
        target_lang = params.get('target_lang', 'EN')
        source_lang = params.get('source_lang', None)
        
        try:
            # Translate the text
            result = self.client.translate_text(
                prompt,
                target_lang=target_lang,
                source_lang=source_lang
            )
            
            return {
                'text': result.text,
                'detected_source_lang': result.detected_source_language,
                'model': f"DeepL Translation ({result.detected_source_language} to {target_lang})"
            }
        except Exception as e:
            logger.error(f"Error in DeepL translation: {e}")
            raise
    
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        """
        DeepL doesn't support chat functionality.
        This method extracts content from the last user message and translates it.
        """
        params = self.default_params.copy()
        params.update(kwargs)
        
        # Extract the last user message
        user_messages = [msg for msg in messages if msg.get('role', '').lower() == 'user']
        if not user_messages:
            raise ValueError("No user messages provided for translation")
            
        last_user_message = user_messages[-1].get('content', '')
        
        # Translate using the complete method
        return self.complete(last_user_message, **params)
    
    def embeddings(self, text: Union[str, List[str]], **kwargs) -> Dict[str, Any]:
        """
        DeepL doesn't support embeddings
        """
        raise NotImplementedError("DeepL translation API does not support embeddings")
    
    def function_call(self, messages: List[Dict[str, str]], functions: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
        """
        DeepL doesn't support function calling
        """
        raise NotImplementedError("DeepL translation API does not support function calling")


class LLMClientFactory:
    """Factory for creating LLM clients."""
    
    @classmethod
    def get_default_model(cls, provider: str) -> str:
        """
        Get default model for a provider
        
        Args:
            provider (str): Provider name
            
        Returns:
            str: Default model name
        """
        provider_model_map = {
            LLMProvider.ANTHROPIC: getattr(settings, 'CLAUDE_MODEL', ModelName.CLAUDE_3_SONNET),
            LLMProvider.DEEPSEEK: getattr(settings, 'DEEPSEEK_MODEL', "deepseek-chat"),
            LLMProvider.OPENAI: getattr(settings, 'OPENAI_MODEL', "gpt-4"),
            LLMProvider.MISTRAL: getattr(settings, 'MISTRAL_MODEL', "mistral-medium"),
            LLMProvider.GOOGLE: getattr(settings, 'GOOGLE_MODEL', "gemini-pro"),
            LLMProvider.OLLAMA: getattr(settings, 'OLLAMA_MODEL', "llama3")
        }
        
        return provider_model_map.get(provider, "")
    
    @classmethod
    def get_default_params(cls, provider: str) -> Dict[str, Any]:
        """
        Get default parameters for a provider
        
        Args:
            provider (str): Provider name
            
        Returns:
            Dict[str, Any]: Default parameters
        """
        default_params = {
            "temperature": getattr(settings, 'LLM_TEMPERATURE', 0.7),
            "max_tokens": getattr(settings, 'LLM_MAX_TOKENS', 1000)
        }
        
        # Provider-specific parameter overrides
        if provider == LLMProvider.ANTHROPIC:
            default_params.update({
                "temperature": getattr(settings, 'CLAUDE_TEMPERATURE', default_params["temperature"]),
                "max_tokens": getattr(settings, 'CLAUDE_MAX_TOKENS', default_params["max_tokens"])
            })
        elif provider == LLMProvider.DEEPSEEK:
            default_params.update({
                "temperature": getattr(settings, 'DEEPSEEK_TEMPERATURE', default_params["temperature"]),
                "max_tokens": getattr(settings, 'DEEPSEEK_MAX_TOKENS', default_params["max_tokens"])
            })
        
        return default_params
    
        
    @classmethod
    def create(cls, provider: str, model: Optional[str] = None, api_key: Optional[str] = None, 
              default_params: Optional[Dict[str, Any]] = None) -> BaseLLMClient:
        """
        Create an LLM client based on provider.
        
        Args:
            provider: The LLM provider (e.g., 'anthropic', 'deepseek')
            model: Model name to use (will use settings-based default if None)
            api_key: Optional API key override (will use from settings if None)
            default_params: Optional parameter overrides
            
        Returns:
            BaseLLMClient instance
            
        Raises:
            ValueError: If provider is not supported
        """
        # Get default model if not specified
        if model is None:
            model = cls.get_default_model(provider)
        
        # Get default parameters
        params = cls.get_default_params(provider)
        
        # Override with provided parameters
        if default_params:
            params.update(default_params)
        
        # Create client based on provider
        if provider == LLMProvider.ANTHROPIC:
            return AnthropicClient(
                provider=provider,
                model=model,
                api_key=api_key,
                default_params=params
            )
        elif provider == LLMProvider.DEEPSEEK:
            return DeepseekClient(
                provider=provider,
                model=model,
                api_key=api_key,
                default_params=params
            )
        elif provider == LLMProvider.DEEPL:
            return DeepLClient(
                provider=provider,
                model=model,
                api_key=api_key,
                default_params=params
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")