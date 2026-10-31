"""
LLM service for AI operations using Groq.
Provides a reusable ChatGroq instance configured with project defaults.
"""

from typing import Optional
from langchain_groq import ChatGroq
from ai.config import get_settings


# Default model and parameters.
# llama-3.3-70b-versatile returns Groq 404 model_not_found for this account.
# openai/gpt-oss-120b is available and returns a valid SearchIntent.
DEFAULT_MODEL = "openai/gpt-oss-120b"
DEFAULT_TEMPERATURE = 0  # Deterministic responses for consistency


def get_llm(
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    **kwargs
) -> ChatGroq:
    """
    Get a configured ChatGroq LLM instance.
    
    This is the single source for LLM configuration across the AI service.
    All LangGraph nodes, MCP tools, and API endpoints should use this function.
    
    Args:
        model: Groq model name. Defaults to openai/gpt-oss-120b
        temperature: Sampling temperature (0-2). Defaults to 0 for deterministic output
        max_tokens: Maximum tokens in response. Uses Groq default if None
        **kwargs: Additional parameters passed to ChatGroq
    
    Returns:
        Configured ChatGroq instance
    
    Example:
        >>> llm = get_llm()
        >>> response = llm.invoke("Explain this property listing...")
        
        >>> # With custom parameters
        >>> creative_llm = get_llm(temperature=0.7, max_tokens=500)
    """
    settings = get_settings()
    
    # Use defaults if not specified
    model = model or DEFAULT_MODEL
    temperature = temperature if temperature is not None else DEFAULT_TEMPERATURE
    
    # Build configuration
    config = {
        "model": model,
        "temperature": temperature,
        "groq_api_key": settings.GROQ_API_KEY,
        **kwargs
    }
    
    # Add max_tokens if specified
    if max_tokens is not None:
        config["max_tokens"] = max_tokens
    
    return ChatGroq(**config)


def get_structured_llm(
    schema,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    **kwargs
) -> ChatGroq:
    """
    Get a ChatGroq instance configured for structured output.
    
    Used for intent parsing and other tasks requiring JSON schema validation.
    
    Args:
        schema: Pydantic model or JSON schema for structured output
        model: Groq model name. Defaults to openai/gpt-oss-120b
        temperature: Sampling temperature. Defaults to 0
        **kwargs: Additional parameters passed to ChatGroq
    
    Returns:
        ChatGroq instance with structured output binding
    
    Example:
        >>> from pydantic import BaseModel
        >>> 
        >>> class SearchIntent(BaseModel):
        ...     category: str
        ...     max_price: float
        >>> 
        >>> llm = get_structured_llm(SearchIntent)
        >>> result = llm.invoke("Find me a mountain stay under 5000")
        >>> # result will be validated against SearchIntent schema
    """
    llm = get_llm(model=model, temperature=temperature, **kwargs)
    
    # Bind structured output schema
    # This uses LangChain's with_structured_output for schema validation
    return llm.with_structured_output(schema)


# Model information for reference
AVAILABLE_MODELS = {
    "openai/gpt-oss-120b": {
        "description": "Default chat model. Supports structured tool output on the current Groq account.",
        "recommended_for": ["intent_parsing", "ranking", "explanation"]
    },
    "openai/gpt-oss-20b": {
        "description": "Smaller chat model. Supports structured tool output on the current Groq account.",
        "recommended_for": ["intent_parsing", "ranking", "explanation"]
    },
    "qwen/qwen3.8-27b": {
        "description": "Qwen chat model. Supports structured tool output on the current Groq account.",
        "recommended_for": ["intent_parsing", "ranking", "explanation"]
    }
}


def list_models() -> dict:
    """
    Get information about available Groq models.
    
    Returns:
        Dictionary of model names to their metadata
    """
    return AVAILABLE_MODELS


if __name__ == "__main__":
    # Test LLM configuration
    print("Testing Groq LLM configuration...")
    print()
    
    try:
        from ai.config import validate_config
        validate_config()
        
        llm = get_llm()
        print(f"✓ LLM configured successfully")
        print(f"  Model: {DEFAULT_MODEL}")
        print(f"  Temperature: {DEFAULT_TEMPERATURE}")
        print(f"  Provider: Groq")
        print()
        
        print("Available models:")
        for model, info in AVAILABLE_MODELS.items():
            print(f"  - {model}")
            print(f"    {info['description']}")
        print()
        
    except Exception as e:
        print(f"✗ LLM configuration failed: {e}")
        print()
        print("Ensure GROQ_API_KEY is set in the root .env file")
