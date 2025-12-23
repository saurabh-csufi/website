"""List all file search stores in your Gemini account."""
from google import genai
import os

# Get API key from environment variable
api_key = os.environ.get('GEMINI_API_KEY')
if not api_key:
    raise ValueError("Please set the GEMINI_API_KEY environment variable")

client = genai.Client(api_key=api_key)

print("Listing all file search stores...\n")

try:
    stores = client.file_search_stores.list()
    count = 0
    for store in stores:
        count += 1
        print(f"Store {count}:")
        print(f"  Name (ID): {store.name}")
        print(f"  Display Name: {getattr(store, 'display_name', 'N/A')}")
        print(f"  State: {getattr(store, 'state', 'N/A')}")
        print()

    if count == 0:
        print("No file search stores found.")
    else:
        print(f"Total: {count} store(s)")

except Exception as e:
    print(f"Error listing stores: {e}")
    print(f"\nError type: {type(e).__name__}")
