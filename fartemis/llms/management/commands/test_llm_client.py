# fartemis/llm/management/commands/test_llm_client.py
"""
@author: solvire
@date: 2025-03-31

Usage examples:

# Test default provider (uses settings-based configuration)
python manage.py test_llm_client

# Test with a specific provider
python manage.py test_llm_client --provider=deepseek

# Test with a specific model
python manage.py test_llm_client --provider=anthropic --model=claude-3-opus-20240229

# Test specific capabilities
python manage.py test_llm_client --provider=deepseek --tests=chat,function,template

# Test with custom parameters
python manage.py test_llm_client --temperature=0.9 --max-tokens=500

# Test with a custom prompt
python manage.py test_llm_client --prompt="What are three benefits of using Django?"

# Run all tests with verbose output
python manage.py test_llm_client --provider=anthropic --all-tests --verbose
"""
import logging
import importlib
import inspect
from django.core.management.base import BaseCommand
from django.conf import settings

from fartemis.llms.clients import LLMClientFactory
from fartemis.llms.constants import LLMProvider, ModelName

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Test LLM client implementations'

    def add_arguments(self, parser):
        # Provider selection
        parser.add_argument(
            '--provider',
            type=str,
            choices=[p[0] for p in LLMProvider.CHOICES],
            help=f'LLM provider to test (default: from settings)'
        )
        
        # Model selection
        parser.add_argument(
            '--model',
            type=str,
            help='Model to use (provider-specific, uses default if not specified)'
        )
        
        # Test selection
        parser.add_argument(
            '--tests',
            type=str,
            help='Comma-separated list of tests to run (completion,chat,function,template)'
        )
        parser.add_argument(
            '--all-tests',
            action='store_true',
            help='Run all available tests'
        )
        
        # Individual test flags (for backward compatibility)
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
        
        # Test content
        parser.add_argument(
            '--prompt',
            type=str,
            default='Explain the importance of testing software in 2-3 sentences.',
            help='Test prompt for completion'
        )
        
        # LLM parameters
        parser.add_argument(
            '--temperature',
            type=float,
            help='Temperature parameter for generation (override settings)'
        )
        parser.add_argument(
            '--max-tokens',
            type=int,
            help='Maximum tokens to generate (override settings)'
        )
        
        # Output control
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Display detailed information about each test'
        )

    def handle(self, *args, **options):
        try:
            # Extract options
            provider = options['provider'] or getattr(settings, 'DEFAULT_LLM_PROVIDER', LLMProvider.ANTHROPIC)
            
            # Determine which tests to run
            tests_to_run = self._determine_tests(options)
            
            # Create parameter overrides if provided
            default_params = {}
            if options['temperature'] is not None:
                default_params['temperature'] = options['temperature']
            if options['max_tokens'] is not None:
                default_params['max_tokens'] = options['max_tokens']
                
            # Initialize client using factory
            client = LLMClientFactory.create(
                provider=provider,
                model=options['model'],
                default_params=default_params if default_params else None
            )
            
            self.stdout.write(self.style.SUCCESS(
                f"Initialized {LLMProvider.get_display_name(provider)} client with model: {client.model}"
            ))
            
            if options['verbose']:
                self.stdout.write(f"Default parameters: {client.default_params}")
            
            # Run requested tests
            self._run_tests(client, tests_to_run, options)
            
        except Exception as e:
            logger.exception("Error testing LLM client")
            self.stderr.write(self.style.ERROR(f"Error: {str(e)}"))
    
    def _determine_tests(self, options):
        """Determine which tests to run based on options"""
        all_tests = ['completion', 'chat', 'function', 'template']
        
        # If specific tests are provided in comma-separated list
        if options['tests']:
            return [test.strip() for test in options['tests'].split(',')]
        
        # If all-tests flag is set
        if options['all_tests']:
            return all_tests
        
        # Legacy individual test flags
        tests = ['completion']  # Always run completion test
        if options['test_chat']:
            tests.append('chat')
        if options['test_function']:
            tests.append('function')
        if 'template' not in tests:
            tests.append('template')  # Template test is lightweight, include by default
        
        return tests
    
    def _run_tests(self, client, tests, options):
        """Run the specified tests"""
        test_methods = {
            'completion': self._test_completion,
            'chat': self._test_chat,
            'function': self._test_function,
            'template': self._test_template
        }
        
        for test in tests:
            if test in test_methods:
                test_methods[test](client, options)
            else:
                self.stderr.write(self.style.WARNING(f"Unknown test: {test}"))
        
        self.stdout.write(self.style.SUCCESS(
            f"\nCompleted {len(tests)} tests for {client.provider} client"
        ))
    
    def _test_completion(self, client, options):
        """Test basic text completion"""
        self.stdout.write("\nTesting text completion...")
        prompt = options['prompt']
        
        if options['verbose']:
            self.stdout.write(f"Prompt: {prompt}")
        
        try:
            completion_response = client.complete(prompt)
            
            self.stdout.write(self.style.SUCCESS("Completion successful!"))
            self.stdout.write("\nResponse:")
            self.stdout.write("=" * 50)
            self.stdout.write(completion_response['text'])
            self.stdout.write("=" * 50)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Completion test failed: {str(e)}"))
    
    def _test_chat(self, client, options):
        """Test chat completion"""
        self.stdout.write("\nTesting chat completion...")
        
        messages = [
            {"role": "system", "content": "You are a helpful assistant specialized in explaining complex concepts simply."},
            {"role": "user", "content": "What is the difference between supervised and unsupervised learning?"}
        ]
        
        if options['verbose']:
            self.stdout.write(f"Messages: {messages}")
        
        try:
            chat_response = client.chat(messages)
            
            self.stdout.write(self.style.SUCCESS("Chat completion successful!"))
            self.stdout.write("\nResponse:")
            self.stdout.write("=" * 50)
            self.stdout.write(chat_response['text'])
            self.stdout.write("=" * 50)
        except NotImplementedError:
            self.stdout.write(self.style.WARNING(f"Chat completion not implemented for {client.provider}"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Chat test failed: {str(e)}"))
    
    def _test_function(self, client, options):
        """Test function calling"""
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
        
        if options['verbose']:
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
            self.stdout.write(self.style.WARNING(f"Function calling not implemented for {client.provider}"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Function test failed: {str(e)}"))
    
    def _test_template(self, client, options):
        """Test prompt templating"""
        self.stdout.write("\nTesting prompt templating...")
        
        template = "Explain {concept} in terms a {audience} would understand."
        variables = {
            "concept": "quantum computing",
            "audience": "10-year-old"
        }
        
        if options['verbose']:
            self.stdout.write(f"Template: {template}")
            self.stdout.write(f"Variables: {variables}")
        
        try:
            rendered_prompt = client.render_prompt(template, **variables)
            
            if options['verbose']:
                self.stdout.write(f"Rendered prompt: {rendered_prompt}")
            
            template_response = client.complete(rendered_prompt)
            
            self.stdout.write(self.style.SUCCESS("Template completion successful!"))
            self.stdout.write("\nResponse:")
            self.stdout.write("=" * 50)
            self.stdout.write(template_response['text'])
            self.stdout.write("=" * 50)
        except NotImplementedError:
            self.stdout.write(self.style.WARNING(f"Prompt templating not implemented for {client.provider}"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Template test failed: {str(e)}"))
    