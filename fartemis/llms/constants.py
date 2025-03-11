# fartemis/llm/constants.py

class ModelName:
    # Anthropic models
    CLAUDE_3_OPUS = "claude-3-opus-20240229"
    CLAUDE_3_SONNET = "claude-3-sonnet-20240229"
    CLAUDE_3_HAIKU = "claude-3-haiku-20240307"
    
    # OpenAI models
    GPT_4 = "gpt-4"
    GPT_4_TURBO = "gpt-4-turbo-preview"
    GPT_3_5_TURBO = "gpt-3.5-turbo"
    
    # Mistral models
    MISTRAL_LARGE = "mistral-large-latest"
    MISTRAL_MEDIUM = "mistral-medium-latest"
    MISTRAL_SMALL = "mistral-small-latest"
    
    # Google models
    GEMINI_PRO = "gemini-pro"
    
    # Ollama models
    LLAMA_3 = "llama3"


class LLMProvider:
    """LLM provider constants."""
    
    ANTHROPIC = 'anthropic'
    OPENAI = 'openai'  # For future extension
    MISTRAL = "mistral"
    GOOGLE = "google"
    OLLAMA = "ollama"
    
    CHOICES = [
        (ANTHROPIC, 'Anthropic (Claude)'),
        (OPENAI, 'OpenAI (GPT)'),
        (MISTRAL, 'Mistral'),
        (GOOGLE, 'Google (Gemini)'),
        (OLLAMA, 'Ollama'),
    ]
    
    @classmethod
    def get_display_name(cls, provider):
        """Get display name for provider."""
        for choice in cls.CHOICES:
            if choice[0] == provider:
                return choice[1]
        return provider
