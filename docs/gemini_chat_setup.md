# Gemini Chat Interface Setup Guide

This guide explains how to set up and use the Gemini-powered chat interface on the Custom Data Commons homepage.

## Overview

The chat interface allows users to:
- Upload PDF documents and ask questions about them
- Have multi-turn conversations with AI
- Get general assistance powered by Google's Gemini AI

## Files Created/Modified

| File | Description |
|------|-------------|
| `server/routes/gemini/api.py` | Backend API endpoints for Gemini chat |
| `server/routes/gemini/__init__.py` | Python package init file |
| `server/__init__.py` | Updated to register Gemini routes |
| `server/templates/custom_dc/custom/homepage.html` | Chat interface UI |

## API Endpoints

### POST `/api/gemini/chat`

Standard chat endpoint that returns complete responses.

**Request Body:**
```json
{
  "message": "Your question here",
  "history": [
    {"role": "user", "text": "Previous message"},
    {"role": "model", "text": "Previous response"}
  ],
  "document": {
    "data": "base64-encoded-pdf-data",
    "mimeType": "application/pdf"
  },
  "systemInstruction": "Optional system prompt"
}
```

**Response:**
```json
{
  "success": true,
  "response": "AI response text"
}
```

### POST `/api/gemini/chat/stream`

Streaming chat endpoint that returns Server-Sent Events (SSE).

Same request format as `/api/gemini/chat`, but returns streaming chunks.

## Setup Instructions

### Step 1: Get a Gemini API Key

1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Create a new API key
3. Copy the key for the next step

### Step 2: Configure the API Key

**Option A: Add to env.list (Recommended)**

Edit `custom_dc/env.list` and add:
```bash
GEMINI_API_KEY=your-gemini-api-key-here
```

**Option B: Set as environment variable**

```bash
export GEMINI_API_KEY=your-gemini-api-key-here
```

### Step 3: Restart Docker Containers

Stop any running containers:
```bash
docker stop $(docker ps -q)
```

Run the service container with your templates mounted:
```bash
docker run -it \
  --env-file custom_dc/env.list \
  -p 8080:8080 \
  -e DEBUG=true \
  -v $(pwd)/custom_dc/sample/:$(pwd)/custom_dc/sample/ \
  -v $(pwd)/server/templates/custom_dc/custom:/workspace/server/templates/custom_dc/custom \
  -v $(pwd)/static/custom_dc/custom:/workspace/static/custom_dc/custom \
  gcr.io/datcom-ci/datacommons-services:stable
```

### Step 4: Access the Chat Interface

Open your browser and navigate to:
```
http://localhost:8080
```

You should see the chat interface with:
- A header saying "Document Chat Assistant"
- A file upload area for PDFs
- A text input for messages
- Suggestion buttons for common questions

## Features

### PDF Document Upload

- **Drag & Drop**: Drag PDF files directly onto the upload area
- **Click to Browse**: Click the upload area to select files
- **Size Limit**: Maximum 50MB per file (Gemini API limit)
- **Multiple Files**: Can upload multiple PDFs (processes first one per message)

### Chat Capabilities

| Feature | Description |
|---------|-------------|
| Document Q&A | Upload a PDF and ask specific questions about its content |
| Multi-turn Conversation | AI remembers previous messages in the conversation |
| General Chat | Ask questions without uploading documents |
| Markdown Rendering | Responses support bold, italic, code blocks |

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Enter` | Send message |
| `Shift + Enter` | New line in message |

## Customization

### Changing the System Prompt

Edit the `systemInstruction` variable in `homepage.html` (around line 412):

```javascript
const systemInstruction = `Your custom instructions here...`;
```

### Changing the AI Model

Edit `server/routes/gemini/api.py` and modify the `DEFAULT_MODEL` constant:

```python
DEFAULT_MODEL = "gemini-2.5-flash"  # Change to other models like "gemini-2.5-pro"
```

Available models:
- `gemini-2.5-flash` - Fast, good for most use cases
- `gemini-2.5-pro` - More capable, slower
- `gemini-2.0-flash` - Previous generation

### Styling the Chat Interface

All CSS styles are in the `<style>` block within `homepage.html`. Key classes:

| Class | Purpose |
|-------|---------|
| `.gemini-chat-container` | Main container |
| `.chat-messages` | Message list area |
| `.message.user` | User message bubble |
| `.message.assistant` | AI message bubble |
| `.file-drop-zone` | PDF upload area |
| `.chat-input-area` | Input section |

## Troubleshooting

### "Gemini API key not configured" Error

**Cause**: The `GEMINI_API_KEY` environment variable is not set.

**Solution**:
1. Add `GEMINI_API_KEY=your-key` to `custom_dc/env.list`
2. Or pass `-e GEMINI_API_KEY=your-key` to docker run

### "Request timed out" Error

**Cause**: Large PDF or complex query taking too long.

**Solution**:
- Try a smaller PDF (under 20 pages)
- Ask simpler questions
- The timeout is set to 120 seconds

### PDF Upload Not Working

**Cause**: File may be too large or not a valid PDF.

**Solution**:
- Ensure file is under 50MB
- Ensure file has `.pdf` extension
- Check browser console for errors

### Chat Not Responding

**Cause**: Backend API might not be running.

**Solution**:
1. Check Docker container logs: `docker logs <container_id>`
2. Verify the container is running: `docker ps`
3. Check if port 8080 is accessible

## API Reference

### Gemini API Documentation

- [Text Generation](https://ai.google.dev/gemini-api/docs/text-generation)
- [Document Processing](https://ai.google.dev/gemini-api/docs/document-processing)
- [API Reference](https://ai.google.dev/api/generate-content)

### Limits

| Limit | Value |
|-------|-------|
| Max PDF size | 50MB |
| Max PDF pages | 1000 |
| Request timeout | 120 seconds |
| Tokens per page | ~258 |

## Security Considerations

- The API key is stored server-side and never exposed to the client
- File uploads are processed in memory and not persisted
- Conversation history is stored client-side only (in browser memory)
- Consider adding rate limiting for production use
