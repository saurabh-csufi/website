"""Debug script to verify file store access and permissions."""
from google import genai
from google.genai import types
import os
import sys

# Get API key from environment variable
api_key = os.environ.get('GEMINI_API_KEY')
if not api_key:
    raise ValueError("Please set the GEMINI_API_KEY environment variable")

print(f"Using API key: {api_key[:10]}...{api_key[-4:]}")
print()

client = genai.Client(api_key=api_key)

# Get store ID from file or command line
STORE_ID_FILE = os.path.join(os.path.dirname(__file__), ".store_id")

if len(sys.argv) > 1:
    store_id = sys.argv[1]
else:
    if os.path.exists(STORE_ID_FILE):
        with open(STORE_ID_FILE, 'r') as f:
            store_id = f.read().strip()
    else:
        print("No store ID found. Run: python debug_file_store.py <store_id>")
        sys.exit(1)

print(f"Checking store: {store_id}")
print("-" * 50)

# 1. List all stores to verify access
print("\n1. Listing all your file search stores...")
try:
    stores = list(client.file_search_stores.list())
    print(f"   Found {len(stores)} store(s):")
    for s in stores:
        match = " <-- THIS ONE" if s.name == store_id else ""
        print(f"   - {s.name} ({getattr(s, 'display_name', 'N/A')}){match}")
except Exception as e:
    print(f"   ERROR listing stores: {e}")

# 2. Try to get the specific store
print(f"\n2. Getting store details for: {store_id}")
try:
    store = client.file_search_stores.get(name=store_id)
    print(f"   ✓ Store found!")
    print(f"   - Name: {store.name}")
    print(f"   - Display name: {getattr(store, 'display_name', 'N/A')}")
    print(f"   - State: {getattr(store, 'state', 'N/A')}")
except Exception as e:
    print(f"   ✗ ERROR: {e}")
    print(f"\n   Possible causes:")
    print(f"   - Store doesn't exist")
    print(f"   - Wrong API key (store was created with different key)")
    print(f"   - API key doesn't have permission")

# 3. Try a simple file search query
print(f"\n3. Testing file search query...")
try:
    file_search_tool = types.Tool(
        file_search=types.FileSearch(
            file_search_store_names=[store_id]
        )
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="What documents are in this knowledge base? List the topics covered.",
        config=types.GenerateContentConfig(
            tools=[file_search_tool],
            temperature=0.3,
        )
    )
    print(f"   ✓ Query succeeded!")
    print(f"\n   Response: {response.text[:500]}...")
except Exception as e:
    print(f"   ✗ ERROR: {e}")
    print(f"\n   This is likely the same error you see in the browser.")

# 4. Print the API key (masked) for comparison
print("\n" + "=" * 50)
print("IMPORTANT: Compare API keys")
print("=" * 50)
print(f"API key in terminal: {api_key[:10]}...{api_key[-4:]}")
print(f"\nMake sure the EXACT SAME key is entered in the browser!")
print(f"Even one character difference means different project/permissions.")
