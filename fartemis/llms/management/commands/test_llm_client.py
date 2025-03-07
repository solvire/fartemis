# fartemis/llm/management/commands/test_llm_client.py
"""
@author: solvire
@date: 2025-03-02


# Test basic completion with Anthropic (using settings.ANTHROPIC_API_KEY)
python manage.py test_llm_client

# Test with a specific API key
python manage.py test_llm_client --api-key=your-api-key-here

# Test with a specific model
python manage.py test_llm_client --model=claude-3-opus-20240229

# Test chat completion
python manage.py test_llm_client --test-chat

# Test function calling
python manage.py test_llm_client --test-function

# Test with custom parameters
python manage.py test_llm_client --temperature=0.9 --max-tokens=500

# Test with a custom prompt
python manage.py test_llm_client --prompt="What are three benefits of using Django for web development?"

# Run all tests
python manage.py test_llm_client --test-chat --test-function
"""
import logging
from django.core.management.base import BaseCommand
from django.conf import settings

from fartemis.llms.clients import LLMClientFactory
from fartemis.llms.constants import LLMProvider, ModelName

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Test LLM client implementation'

    def add_arguments(self, parser):
        parser.add_argument(
            '--provider',
            type=str,
            default=LLMProvider.ANTHROPIC,
            help='LLM provider to test (default: anthropic)'
        )
        parser.add_argument(
            '--model',
            type=str,
            help='Model to use (provider-specific, uses default if not specified)'
        )
        parser.add_argument(
            '--api-key',
            type=str,
            help='API key (uses settings if not provided)'
        )
        parser.add_argument(
            '--prompt',
            type=str,
            default='Explain the importance of testing software in 2-3 sentences.',
            help='Test prompt for completion'
        )
        parser.add_argument(
            '--test-chat',
            action='store_true',
            help='Test chat completion'
        )
        parser.add_argument(
            '--test-function',
            action='store_true',
            help='Test function calling'
        )
        parser.add_argument(
            '--temperature',
            type=float,
            default=0.7,
            help='Temperature parameter for generation'
        )
        parser.add_argument(
            '--max-tokens',
            type=int,
            default=1000,
            help='Maximum tokens to generate'
        )

    def handle(self, *args, **options):
        try:
            # Get provider
            provider = options['provider']
            
            # Determine which API key to use
            api_key = options['api_key']
            if not api_key:
                if provider == LLMProvider.ANTHROPIC:
                    api_key = settings.ANTHROPIC_API_KEY
                elif provider == LLMProvider.OPENAI:
                    api_key = settings.OPENAI_API_KEY
                else:
                    api_key = getattr(settings, f"{provider.upper()}_API_KEY", None)
            
            if not api_key:
                self.stderr.write(self.style.ERROR(f"No API key provided for {provider}"))
                return
            
            # Initialize client
            self.stdout.write(f"Initializing {provider} client...")
            
            # Set params based on provider
            default_params = {}

            if provider == LLMProvider.ANTHROPIC:
                default_params = {
                    "max_tokens": options['max_tokens'],  # Changed from max_tokens_to_sample
                    "temperature": options['temperature']
                }
            elif provider == LLMProvider.OPENAI:
                default_params = {
                    "max_tokens": options['max_tokens'],
                    "temperature": options['temperature']
                }
            else:
                # Generic params
                default_params = {
                    "max_tokens": options['max_tokens'],
                    "temperature": options['temperature']
                }
            
            client = LLMClientFactory.create(
                provider=provider,
                api_key=api_key,
                model=options['model'],
                default_params=default_params
            )
            
            self.stdout.write(self.style.SUCCESS(f"Initialized {provider} client with model: {client.model}"))
            
            # Test completion
            self.stdout.write("\nTesting text completion...")
            prompt = options['prompt']
            self.stdout.write(f"Prompt: {prompt}")
            
            completion_response = client.complete(prompt)
            
            self.stdout.write(self.style.SUCCESS("Completion successful!"))
            self.stdout.write("\nResponse:")
            self.stdout.write("=" * 50)
            self.stdout.write(completion_response['text'])
            self.stdout.write("=" * 50)
            
            # Test chat if requested
            if options['test_chat']:
                self.stdout.write("\nTesting chat completion...")
                
                messages = [
                    {"role": "system", "content": "You are a helpful assistant specialized in explaining complex concepts simply."},
                    {"role": "user", "content": "What is the difference between supervised and unsupervised learning?"}
                ]
                
                self.stdout.write(f"Messages: {messages}")
                
                chat_response = client.chat(messages)
                
                self.stdout.write(self.style.SUCCESS("Chat completion successful!"))
                self.stdout.write("\nResponse:")
                self.stdout.write("=" * 50)
                self.stdout.write(chat_response['text'])
                self.stdout.write("=" * 50)
            
            # Test function calling if requested
            if options['test_function']:
                self.stdout.write("\nTesting function calling...")
                
                messages = [
                    {"role": "user", "content": "What's the weather in New York?"}
                ]
                
                functions = [
                    {
                        "name": "get_weather",
                        "description": "Get the current weather in a location",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "location": {
                                    "type": "string",
                                    "description": "The city and state"
                                },
                                "unit": {
                                    "type": "string",
                                    "enum": ["celsius", "fahrenheit"],
                                    "description": "Temperature unit"
                                }
                            },
                            "required": ["location"]
                        }
                    }
                ]
                
                self.stdout.write(f"Messages: {messages}")
                self.stdout.write(f"Functions: {functions}")
                
                try:
                    function_response = client.function_call(messages, functions)
                    
                    self.stdout.write(self.style.SUCCESS("Function calling successful!"))
                    self.stdout.write("\nResponse:")
                    self.stdout.write("=" * 50)
                    if 'tool_calls' in function_response:
                        self.stdout.write(f"Tool calls: {function_response['tool_calls']}")
                    if 'text' in function_response and function_response['text']:
                        self.stdout.write(f"Text: {function_response['text']}")
                    self.stdout.write("=" * 50)
                except NotImplementedError:
                    self.stdout.write(self.style.WARNING("Function calling not implemented for this provider"))
            
            # Test prompt templating
            self.stdout.write("\nTesting prompt templating...")
            
            template = "Explain {concept} in terms a {audience} would understand."
            variables = {
                "concept": "quantum computing",
                "audience": "10-year-old"
            }
            
            self.stdout.write(f"Template: {template}")
            self.stdout.write(f"Variables: {variables}")
            
            rendered_prompt = client.render_prompt(template, **variables)
            self.stdout.write(f"Rendered prompt: {rendered_prompt}")
            
            template_response = client.complete(rendered_prompt)
            
            self.stdout.write(self.style.SUCCESS("Template completion successful!"))
            self.stdout.write("\nResponse:")
            self.stdout.write("=" * 50)
            self.stdout.write(template_response['text'])
            self.stdout.write("=" * 50)
            
            self.stdout.write(self.style.SUCCESS(f"\nAll tests completed successfully for {provider}!"))
            
        except Exception as e:
            logger.exception("Error testing LLM client")
            self.stderr.write(self.style.ERROR(f"Error: {str(e)}"))