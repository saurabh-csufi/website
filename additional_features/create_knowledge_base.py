from google import genai
import os

# Get API key from environment variable
api_key = os.environ.get('GEMINI_API_KEY')
if not api_key:
    raise ValueError("Please set the GEMINI_API_KEY environment variable")

client = genai.Client(api_key=api_key)

# Configuration
STORE_NAME = 'msme_policies'
PDF_FOLDER = os.path.join(os.path.dirname(__file__), "RAG_Corpus")
STORE_ID_FILE = os.path.join(os.path.dirname(__file__), ".store_id")

def create_store():
    """Create a new file search store and upload all PDFs."""
    # 1. Create the persistent store
    store = client.file_search_stores.create(
        config={'display_name': STORE_NAME}
    )
    store_id = store.name
    print(f"Store created! ID: {store_id}")

    # Save store ID to file for future use
    with open(STORE_ID_FILE, 'w') as f:
        f.write(store_id)
    print(f"Store ID saved to {STORE_ID_FILE}")

    # 2. Upload all PDFs
    pdf_files = [f for f in os.listdir(PDF_FOLDER) if f.endswith(".pdf")]
    total = len(pdf_files)

    for i, filename in enumerate(pdf_files, 1):
        path = os.path.join(PDF_FOLDER, filename)
        print(f"[{i}/{total}] Uploading {filename}...")
        try:
            client.file_search_stores.upload_to_file_search_store(
                file=path,
                file_search_store_name=store_id
            )
        except Exception as e:
            print(f"  Error uploading {filename}: {e}")
            continue

    print(f"\nAll {total} documents uploaded to store: {store_id}")
    return store_id

def get_store_id():
    """Get the saved store ID, or None if not created yet."""
    if os.path.exists(STORE_ID_FILE):
        with open(STORE_ID_FILE, 'r') as f:
            return f.read().strip()
    return None

if __name__ == "__main__":
    existing_id = get_store_id()
    if existing_id:
        print(f"Store already exists: {existing_id}")
        print("Delete .store_id file to create a new store.")
    else:
        create_store()