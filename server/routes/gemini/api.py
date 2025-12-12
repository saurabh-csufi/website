# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Gemini Chat API routes for Custom Data Commons."""

import base64
import json
import logging

from flask import Blueprint
from flask import current_app
from flask import request
from flask import Response
from flask import stream_with_context
import requests

bp = Blueprint('gemini_api', __name__, url_prefix='/api/gemini')

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-2.5-flash"


@bp.route('/chat', methods=['POST'])
def chat():
  """Handle chat requests to Gemini API.

  Expects JSON body with:
    - message: string (required) - The user's message
    - history: array (optional) - Previous conversation history
    - document: object (optional) - {data: base64, mimeType: string}

  Returns:
    JSON response with the model's reply
  """
  api_key = current_app.config.get('GEMINI_API_KEY')
  if not api_key:
    return {'error': 'Gemini API key not configured'}, 500

  data = request.get_json()
  if not data:
    return {'error': 'Request body is required'}, 400

  message = data.get('message', '')
  history = data.get('history', [])
  document = data.get('document')
  system_instruction = data.get('systemInstruction', '')

  if not message and not document:
    return {'error': 'Message or document is required'}, 400

  # Build the contents array
  contents = []

  # Add conversation history
  for item in history:
    contents.append({
        'role': item.get('role', 'user'),
        'parts': [{
            'text': item.get('text', '')
        }]
    })

  # Build current message parts
  current_parts = []

  # Add document if provided
  if document:
    current_parts.append({
        'inline_data': {
            'mime_type': document.get('mimeType', 'application/pdf'),
            'data': document.get('data', '')
        }
    })

  # Add text message
  if message:
    current_parts.append({'text': message})

  contents.append({'role': 'user', 'parts': current_parts})

  # Build request payload
  payload = {'contents': contents}

  # Add system instruction if provided
  if system_instruction:
    payload['system_instruction'] = {'parts': [{'text': system_instruction}]}

  # Add generation config
  payload['generationConfig'] = {
      'temperature': 1.0,
      'topP': 0.95,
      'topK': 40,
  }

  # Make request to Gemini API
  url = f"{GEMINI_API_BASE}/{DEFAULT_MODEL}:generateContent"
  headers = {'Content-Type': 'application/json', 'x-goog-api-key': api_key}

  try:
    response = requests.post(url, headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    result = response.json()

    # Extract text from response
    candidates = result.get('candidates', [])
    if candidates:
      parts = candidates[0].get('content', {}).get('parts', [])
      if parts:
        text = parts[0].get('text', '')
        return {'response': text, 'success': True}

    return {'error': 'No response from model', 'success': False}, 500

  except requests.exceptions.Timeout:
    logging.error('Gemini API request timed out')
    return {'error': 'Request timed out'}, 504
  except requests.exceptions.RequestException as e:
    logging.error(f'Gemini API request failed: {e}')
    return {'error': str(e)}, 500


@bp.route('/chat/stream', methods=['POST'])
def chat_stream():
  """Handle streaming chat requests to Gemini API.

  Same request format as /chat but returns Server-Sent Events.
  """
  api_key = current_app.config.get('GEMINI_API_KEY')
  if not api_key:
    return {'error': 'Gemini API key not configured'}, 500

  data = request.get_json()
  if not data:
    return {'error': 'Request body is required'}, 400

  message = data.get('message', '')
  history = data.get('history', [])
  document = data.get('document')
  system_instruction = data.get('systemInstruction', '')

  if not message and not document:
    return {'error': 'Message or document is required'}, 400

  # Build the contents array
  contents = []

  # Add conversation history
  for item in history:
    contents.append({
        'role': item.get('role', 'user'),
        'parts': [{
            'text': item.get('text', '')
        }]
    })

  # Build current message parts
  current_parts = []

  # Add document if provided
  if document:
    current_parts.append({
        'inline_data': {
            'mime_type': document.get('mimeType', 'application/pdf'),
            'data': document.get('data', '')
        }
    })

  # Add text message
  if message:
    current_parts.append({'text': message})

  contents.append({'role': 'user', 'parts': current_parts})

  # Build request payload
  payload = {'contents': contents}

  # Add system instruction if provided
  if system_instruction:
    payload['system_instruction'] = {'parts': [{'text': system_instruction}]}

  # Add generation config
  payload['generationConfig'] = {
      'temperature': 1.0,
      'topP': 0.95,
      'topK': 40,
  }

  def generate():
    url = f"{GEMINI_API_BASE}/{DEFAULT_MODEL}:streamGenerateContent?alt=sse"
    headers = {'Content-Type': 'application/json', 'x-goog-api-key': api_key}

    try:
      with requests.post(url,
                         headers=headers,
                         json=payload,
                         stream=True,
                         timeout=120) as response:
        response.raise_for_status()
        for line in response.iter_lines():
          if line:
            line_str = line.decode('utf-8')
            if line_str.startswith('data: '):
              json_str = line_str[6:]
              try:
                chunk = json.loads(json_str)
                candidates = chunk.get('candidates', [])
                if candidates:
                  parts = candidates[0].get('content', {}).get('parts', [])
                  if parts:
                    text = parts[0].get('text', '')
                    if text:
                      yield f"data: {json.dumps({'text': text})}\n\n"
              except json.JSONDecodeError:
                continue
      yield "data: [DONE]\n\n"
    except Exception as e:
      logging.error(f'Gemini streaming request failed: {e}')
      yield f"data: {json.dumps({'error': str(e)})}\n\n"

  return Response(stream_with_context(generate()),
                  mimetype='text/event-stream',
                  headers={
                      'Cache-Control': 'no-cache',
                      'Connection': 'keep-alive',
                      'X-Accel-Buffering': 'no'
                  })
