"""
Query the PDF knowledge base using Gemini's file search.
The PDFs must first be uploaded using create_knowledge_base.py
"""
from google import genai
from google.genai import types
import os

# Get API key from environment variable
api_key = os.environ.get('GEMINI_API_KEY')
if not api_key:
    raise ValueError("Please set the GEMINI_API_KEY environment variable")

client = genai.Client(api_key=api_key)

# Configuration
STORE_ID_FILE = os.path.join(os.path.dirname(__file__), ".store_id")
MODEL = "gemini-2.5-flash"  # File search requires Gemini 2.5 models

def get_store_id():
    """Get the saved store ID."""
    if os.path.exists(STORE_ID_FILE):
        with open(STORE_ID_FILE, 'r') as f:
            return f.read().strip()
    raise ValueError(
        "No store ID found. Run create_knowledge_base.py first to upload PDFs."
    )

def query(user_query: str, system_instruction: str = None) -> dict:
    """
    Query the knowledge base with a user question.

    Args:
        user_query: The user's question
        system_instruction: Optional system prompt to guide the model

    Returns:
        dict with 'response' (text) and 'sources' (list of source info)
    """
    store_id = get_store_id()

    # Default system instruction if none provided
    if not system_instruction:
        system_instruction = """You are a helpful assistant that answers questions
based on the uploaded documents. Always cite which document your information
comes from. If the answer is not found in the documents, say so clearly."""

    # Configure file search tool with the store
    file_search_tool = types.Tool(
        file_search=types.FileSearch(
            file_search_store_names=[store_id]
        )
    )

    # Generate response with file search
    response = client.models.generate_content(
        model=MODEL,
        contents=user_query,
        config=types.GenerateContentConfig(
            tools=[file_search_tool],
            system_instruction=system_instruction,
            temperature=0.3,
        )
    )

    # Extract text and any grounding metadata
    result = {
        'response': response.text,
        'sources': []
    }

    # Try to extract source information from grounding metadata
    if hasattr(response, 'candidates') and response.candidates:
        candidate = response.candidates[0]
        if hasattr(candidate, 'grounding_metadata'):
            metadata = candidate.grounding_metadata
            if hasattr(metadata, 'grounding_chunks'):
                for chunk in metadata.grounding_chunks:
                    if hasattr(chunk, 'retrieved_context'):
                        result['sources'].append({
                            'title': getattr(chunk.retrieved_context, 'title', 'Unknown'),
                            'uri': getattr(chunk.retrieved_context, 'uri', None)
                        })

    return result

def chat(system_instruction: str = None):
    """
    Interactive chat session with the knowledge base.

    Args:
        system_instruction: Optional system prompt
    """
    store_id = get_store_id()
    print(f"Connected to store: {store_id}")
    print("Type 'quit' or 'exit' to end the session.\n")

    if not system_instruction:
        system_instruction = """You are a helpful assistant that answers questions
based on the uploaded documents about trade agreements, policies, and regulations.
Always cite which document your information comes from. If the answer is not found
in the documents, say so clearly."""

    file_search_tool = types.Tool(
        file_search=types.FileSearch(
            file_search_store_names=[store_id]
        )
    )

    # Create a chat session
    chat_session = client.chats.create(
        model=MODEL,
        config=types.GenerateContentConfig(
            tools=[file_search_tool],
            system_instruction=system_instruction,
            temperature=0.3,
        )
    )

    while True:
        try:
            user_input = input("\nYou: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ['quit', 'exit']:
                print("Goodbye!")
                break

            response = chat_session.send_message(user_input)
            print(f"\nAssistant: {response.text}")

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}")

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        # Single query mode
        question = " ".join(sys.argv[1:])
        result = query(question)
        print(f"Answer: {result['response']}")
        if result['sources']:
            print("\nSources:")
            for src in result['sources']:
                print(f"  - {src['title']}")
    else:
        # Interactive chat mode
        chat()
