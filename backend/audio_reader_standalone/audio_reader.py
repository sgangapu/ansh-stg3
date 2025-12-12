import os
import PyPDF2
import google.generativeai as genai
from cartesia import Cartesia
from typing import Dict, List, Optional, Callable, Union
import json
from dotenv import load_dotenv
import logging
import atexit
import requests
import io
import wave
import soundfile as sf
import time
import uuid
import websockets
import base64
import asyncio
import numpy as np
try:
    from pymongo import MongoClient
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    MongoClient = None

# Load .env file from current directory or parent directory
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=env_path)
# Also try loading from current directory (for backwards compatibility)
load_dotenv()

voicesUrl = "https://api.cartesia.ai/voices/"

# Configure logging (respect LOG_LEVEL env if provided)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger(__name__)

class AudiobookReaderContinuous:
    def __init__(self):
        self.cartesia_api_key = os.environ.get("CARTESIA_API_KEY")
        self.gemini_api_key = os.environ.get("GOOGLE_API_KEY")

        if not self.cartesia_api_key:
            raise ValueError("CARTESIA_API_KEY environment variable is not set")
        if not self.gemini_api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is not set")

        try:
            self.cartesia_client = Cartesia(api_key=self.cartesia_api_key)
            logger.info("Cartesia client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Cartesia client: {e}")
            raise ValueError(f"Failed to initialize Cartesia client: {e}")

        genai.configure(api_key=self.gemini_api_key)
        self.gemini_model = genai.GenerativeModel('gemini-2.5-pro') 
        
        # Try both X-API-Key and Authorization Bearer headers for compatibility
        headers = {
            "Cartesia-Version": "2024-06-10",
            "X-API-Key": self.cartesia_api_key,
            "Authorization": f"Bearer {self.cartesia_api_key}"
        }
        try:
            response = requests.get(voicesUrl, headers=headers)
            
            if response.status_code == 401:
                error_msg = response.text.strip() if response.text else "Unauthorized"
                logger.error(f"Cartesia API authentication failed (401): {error_msg}")
                logger.error(f"API Key format check - starts with 'sk_car_': {self.cartesia_api_key.startswith('sk_car_')}")
                logger.error(f"API Key length: {len(self.cartesia_api_key)}")
                raise ValueError(
                    f"Invalid Cartesia API key. Please check your CARTESIA_API_KEY environment variable.\n"
                    f"Get a valid API key from: https://console.cartesia.ai/\n"
                    f"Error: {error_msg}"
                )
            
            response.raise_for_status()
            
            if not response.text or response.text.strip() == "":
                logger.error(f"Empty response from Cartesia API. Status: {response.status_code}")
                raise ValueError(f"Cartesia API returned empty response (Status: {response.status_code})")
            
            logger.info(f"Cartesia API response status: {response.status_code}, content length: {len(response.text)}")
            self.available_voices = response.json()
            
            if not self.available_voices:
                logger.warning("Cartesia API returned empty voices list")
                self.available_voices = []
                
        except requests.exceptions.HTTPError as e:
            error_msg = response.text[:200] if 'response' in locals() and response.text else str(e)
            logger.error(f"HTTP error from Cartesia API (Status {response.status_code if 'response' in locals() else 'unknown'}): {error_msg}")
            raise ValueError(f"Cartesia API error (Status {response.status_code if 'response' in locals() else 'unknown'}): {error_msg}")
        except requests.exceptions.JSONDecodeError as e:
            response_text = response.text[:500] if 'response' in locals() and response.text else 'N/A'
            logger.error(f"Failed to parse JSON from Cartesia API. Response text: {response_text}")
            raise ValueError(f"Cartesia API returned invalid JSON. Check your API key and network connection. Error: {str(e)}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error when fetching voices from Cartesia API: {e}")
            raise ValueError(f"Failed to fetch voices from Cartesia API: {str(e)}")

        # Filter voices: only emotive English voices for better performance
        # Hardcoded list of emotive voice names from Cartesia's voice library
        emotive_voice_names = {
            'Tessa', 'Kiefer', 'Brandon', 'Ariana', 'Dorothy', 'Joanie', 'Layla', 'Marian',
            'Cory', 'Kyle', 'Sean', 'Ross', 'Clint', 'Celine', 'Judith', 'Suzanne', 'Edward',
            'Tabitha', 'Elaine', 'Sterling', 'Regis', 'Tanner', 'Marcus', 'Colin', 'Skyler',
            'Cameron', 'Sabrina', 'Emily', 'Shelly', 'Laurel', 'Jeremy', 'Kurt', 'Zander',
            'Jillian', 'Garrett', 'Romeo', 'Marjorie', 'Noah', 'Kim', 'Ariane', 'Kelsey',
            'Maxine', 'Aubrey', 'Wesley', 'Rory', 'Isla', 'Janice', 'Steven', 'Melina',
            'Dominic', 'Aina', 'Vivian', 'Holly', 'Mason', 'Spencer', 'Conrad', 'Derrick',
            'Clarkson', 'Vicky', 'Melanie', 'Quinn', 'Bryce', 'Marvin', 'Tiffany', 'Elliott',
            'Jamie', 'Preston', 'Aiden', 'Kelly', 'Patricia', 'Diana', 'Colby', 'Harley',
            'Logan', 'Selene', 'Tara', 'Evelyn', 'Marge', 'Benji', 'Zoey', 'Chandler',
            'Mindy', 'Darius', 'Kayla', 'Graham', 'Harlan', 'Wade', 'Devin', 'Sasha',
            'Dylan', 'Shane', 'Lawson', 'Haley', 'Julian', 'Gavin', 'Denise', 'Carl',
            'Jett', 'Edna', 'Caleb', 'Orin', 'Dean', 'Lacey', 'Dana', 'Cera', 'Donny',
            'Elise', 'Reese', 'Ralph', 'Damon', 'Jace', 'Edric', 'Clark', 'Leo', 'Hugh',
            'Ronan', 'Arvin', 'Nora', 'Maya', 'Lira'
        }
        
        emotive_voices = []
        if self.available_voices:
            for voice in self.available_voices:
                voice_name = voice.get('name', '')
                language = voice.get('language', '').lower()
                if language == 'en' and voice_name in emotive_voice_names:
                    emotive_voices.append(voice)
        
        logger.info(f"Filtered to {len(emotive_voices)} Emotive English voices (from {len(self.available_voices)} total)")
        
        self.voices_prompt = "Available voices (all are English and optimized for emotional expression):\n"
        if emotive_voices:
            for voice in emotive_voices:
                voice_id = voice.get('id', 'unknown')
                voice_name = voice.get('name', 'Unknown')
                description = voice.get('description', 'No description')
                self.voices_prompt += f"ID: {voice_id}, Name: {voice_name}, Description: {description}\n"
        else:
            logger.warning("No Emotive English voices found in API - using all English voices as fallback")
            self.voices_prompt = "Available voices (all are English):\n"
            for voice in self.available_voices:
                if voice.get('language', '').lower() == 'en':
                    voice_id = voice.get('id', 'unknown')
                    voice_name = voice.get('name', 'Unknown')
                    description = voice.get('description', 'No description')
                    self.voices_prompt += f"ID: {voice_id}, Name: {voice_name}, Description: {description}\n"

        # Cartesia-supported emotions (primary emotions with best results)
        # Only these 6 emotions are production-ready, others are beta
        self.primary_emotions = [
            "neutral", "angry", "excited", "content", "sad", "scared"
        ]

        self.sample_rate = 44100  # Updated to match new SDK default
        self.audio_chunks = []

        # MongoDB connection (lazy initialization)
        self.mongo_client = None
        self.mongo_db = None
        self.mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
        self.db_name = os.getenv("MONGO_DB_NAME", "audiobooks_db")

        atexit.register(self.cleanup)

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extract text content from a PDF file."""
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text()
            return text
        except Exception as e:
            logger.error(f"Error reading PDF file: {str(e)}")
            raise

    def connect_to_mongodb(self):
        """Initialize MongoDB connection if not already connected."""
        if not MONGODB_AVAILABLE:
            raise ValueError("pymongo is not installed. Install it with: pip install -r requirements_mongo.txt")
        
        if self.mongo_client is None:
            try:
                self.mongo_client = MongoClient(self.mongo_uri)
                self.mongo_db = self.mongo_client[self.db_name]
                self.mongo_client.server_info()
                logger.info(f"Connected to MongoDB: {self.db_name}")
            except Exception as e:
                logger.error(f"Failed to connect to MongoDB: {e}")
                raise ValueError(f"MongoDB connection failed: {e}")

    def fetch_segments_from_mongodb(self, book_id: str) -> List[Dict]:
        """
        Fetch segments for a book from MongoDB.
        
        Args:
            book_id: The book ID to fetch segments for
            
        Returns:
            List of segment dictionaries with speaker, text, voice_id, etc.
        """
        self.connect_to_mongodb()
        
        try:
            book = self.mongo_db.books.find_one({"book_id": book_id})
            if not book:
                raise ValueError(f"Book '{book_id}' not found in MongoDB")
            
            logger.info(f"Found book: {book.get('title', book_id)}")
            
            segments_cursor = self.mongo_db.segments.find(
                {"book_id": book_id}
            ).sort("segment_index", 1)
            
            segments = []
            for seg in segments_cursor:
                segment = {
                    "speaker": seg.get("speaker", "unknown"),
                    "original_text": seg.get("original_text", ""),
                    "text": seg.get("translated_text", seg.get("text", "")),  # Use translated_text with SSML tags
                    "voice_id": seg.get("voice_id"),
                    "emotion": seg.get("emotion", "neutral"),
                    "has_laughter": seg.get("has_laughter", False),
                    "language": seg.get("language", "en")
                }
                segments.append(segment)
            
            logger.info(f"Loaded {len(segments)} segments from MongoDB for book '{book_id}'")
            return segments
            
        except Exception as e:
            logger.error(f"Error fetching segments from MongoDB: {e}")
            raise

    def analyze_text_and_assign_voices_with_gemini(self, text: str, language: str) -> List[Dict]:
        """
        Use Gemini API to analyze text, identify speakers, and assign voice IDs in one step.
        Returns a list of dictionaries containing speaker, text, and voice ID information.
        """
        try:
            prompt = f"""

SYSTEM INSTRUCTION (READ CAREFULLY AND FOLLOW EXACTLY)



# IDENTITY / ROLE



You are an expert audiobook narrator, dialogue director, and Cartesia Sonic-3 TTS specialist.



# CORE TASK



Given the input text, you MUST:



1. Break the text into segments.

2. Analyze, clean, and normalize each segment.

3. Identify speakers and scenes.

4. Assign voices and emotions.

5. Apply SSML and continuation spacing rules.

6. Output ONLY a valid JSON array describing how each segment should be spoken.



You MUST strictly follow all formatting, segmentation, and SSML rules.

You MUST obey every constraint in this prompt.

Your output MUST be complete, correct, and valid JSON.

Do NOT include commentary, explanations, markdown, or anything outside the JSON array.



=====================================================================

# OUTPUT FORMAT (BINDING CONTRACT)

=====================================================================



Output prefix (required, exact):



JSON:



Immediately after that prefix, output ONLY a valid JSON array.



Each item in the JSON array MUST have EXACTLY these fields and NO others:



{{

  "speaker": "string",

  "original_text": "string",

  "translated_text": "string (begins with <emotion .../>)",

  "voice_id": "UUID string from voices list",

  "emotion": "neutral|angry|excited|content|sad|scared",

  "has_laughter": boolean,

  "needs_break": boolean,

  "scene_id": "string (e.g. 'scene_1')"

}}



Rules:



- NO additional fields.

- NO null values.

- NO missing punctuation.

- NO newline characters in any field.

- Everything must be one line per string.

- The response MUST be pure JSON (after the prefix) with no extra text.



=====================================================================

# TASK OVERVIEW (STRICT)

=====================================================================



For the provided text, you MUST:



- Break the text into segments.

- Analyze each segment.

- Clean and normalize text.

- Assign speaker.

- Assign voice (voice_id from the provided voices list).

- Detect emotion.

- Apply SSML.

- Apply continuation spacing rules.

- Produce the final JSON array.



Follow ALL rules below.



=====================================================================

# 1. SEGMENTATION RULES

=====================================================================



Break text into natural speech units at:



- Sentence boundaries (. ! ?)

- Speaker changes or new dialogue

- Major narrative transitions

- Natural breaths or pause points



Each segment MUST:



- Represent a complete spoken thought.

- Contain one stable emotion.

- Be joinable with others according to continuation rules.

- End with punctuation (., !, ?).



=====================================================================

# 2. TEXT CLEANUP RULES

=====================================================================



REMOVE:



- Stage directions describing physical actions:

  "(walks away)", "(opens door)", "(smiles)", "(breathing heavily)"

- Empty parentheticals or shorthand stage directions.

- Titles, scene headers, character lists, and script metadata such as:

  - Play titles

  - "Characters:"

  - "Scene 1"

  - Any header text that is not meant to be spoken.



KEEP:



- ALL narrative tags and dialogue attributions

  (e.g., "he said", "she shouted happily", "they laughed").

- These MUST be included in the "translated_text" so the narrator speaks them.

- Only remove text that is strictly a stage direction or metadata

  (e.g. "Scene 1", "(Enter Stage Left)").



OTHER RULES:



- NO newline characters in any field.

- Normalize whitespace → single spaces only.

- Preserve punctuation and capitalization.

- ALWAYS end with punctuation.



Parentheticals describing tone/emotion (e.g., "(whispering)", "(angrily)"):



- Remove them from the text ONLY if they are standalone instructions not meant to be spoken.

- If part of a narrative sentence (e.g. "he said (angrily)"), keep the "he said" part and ONLY remove the parenthetical if it breaks the flow.

- BETTER: Incorporate the implied emotion into the 'emotion' field and keep the text natural.



=====================================================================

# 3. SPEAKER IDENTIFICATION

=====================================================================



Rules:



- Use explicit labels when present.

- If unlabeled, infer speaker from quoted dialogue and context.

- Use "narrator" for:

  * Scenes

  * Descriptions

  * Internal thoughts (unless explicitly attributed to a character).

- Group voices when needed → e.g., "Pig 1 & Pig 2".

- Speaker names MUST remain consistent across all segments.



=====================================================================

# 4. SCENE IDENTIFICATION (NEW & CRITICAL)

=====================================================================



You MUST group segments into "scenes" based on narrative flow.



- A "scene" is a continuous block of time/action.

- Assign a `scene_id` (e.g., "scene_1", "scene_2") to every segment.



Start a new scene when:



- Time passes (e.g., "The next day...").

- Location changes (e.g., "Meanwhile, at the castle...").

- A major mood shift occurs.



Additional rules:



- Segments within a scene will be generated sequentially for smooth prosody.

- Different scenes may be generated in parallel.



=====================================================================

# 5. VOICE SELECTION RULES (MANDATORY)

=====================================================================



Match voices based on personality cues:



- Children → "young", "playful", "bright"

- Villains → "deep", "intense", "authoritative"

- Gentle characters → "warm", "soothing", "friendly"

- Narrators → "neutral", "clear", "versatile"



Rules:



- One speaker = one voice_id (consistent across all segments for that speaker).

- You MUST choose voice_id values from the provided voices list.

- If there is no perfect match → choose a neutral compatible voice.

- Prefer voices tagged "Emotive" for better emotion response.



=====================================================================

# 6. EMOTION SELECTION (STRICT — ONLY 6 EMOTIONS ALLOWED)

=====================================================================



Allowed emotions:



- neutral

- angry

- excited

- content

- sad

- scared



Choose emotion using:



- Emotion words (e.g., "furious", "terrified", "delighted").

- Delivery cues (whisper = sad/neutral; shout = excited/angry).

- Punctuation:

  - "!" → angry/excited

  - "…" → sad

  - "?" → usually neutral (unless context suggests otherwise).

- Story context:

  - Danger → scared

  - Joy → excited

  - Calm → content or neutral.



DEFAULT emotion = **neutral**.



DO NOT use any emotion not in the allowed list.



=====================================================================

# 7. SSML RULES

=====================================================================



## Emotion Tag (MANDATORY)



Every "translated_text" MUST begin with:



  `<emotion value="EMOTION" />`



Where EMOTION matches the "emotion" field (neutral, angry, excited, content, sad, scared).



## Break Tags (USE SPARINGLY)



Use ONLY when `"needs_break": true`.



Allowed break tags:



- `<break time="1s"/>`

- `<break time="1.5s"/>`



Use break tags for:



- Scene shifts.

- Dramatic pauses.

- Explicit pauses in text (e.g., "He paused.").



## Laughter



- Insert `[laughter]` in "translated_text" when appropriate.

- When you insert `[laughter]`, you MUST set `"has_laughter": true`.



## Spell-out Tag (Optional, Allowed)



You MAY use:



- `<spell>ABC123</spell>` for acronyms, numbers, IDs that must be spelled out.



=====================================================================

# 8. CUSTOM PRONUNCIATION (Sonic-3 Feature)

=====================================================================



You MAY add custom pronunciation for difficult words.



Two allowed forms:



### A) IPA / MFA-style phonemes



- Use the format: `<<phoneme|phoneme|phoneme>>`

- No whitespace inside the brackets.

- One word per bracket.



Example:



- `<<kʰ|ɑ|ɹ|tʲ|i|ʒ|ɐ>>`



### B) Sounds-like Guidance



- A plaintext alternate pronunciation, e.g.:

  - "chop-uh-TOO-liss"



Rules:



- Only use when needed (proper nouns, fantasy names, technical terms).

- Replace the original word in "translated_text" with the custom pronunciation block.

- The result MUST remain pronounceable.



=====================================================================

# 9. CONTINUATION SPACING RULES (CRITICAL FOR CARTESIA)

=====================================================================



You MUST follow these rules for joinable segments:



If a segment ends with one of: `. ! ?`



→ The next segment MUST start with **one leading space**.



If a segment ends with a comma or is mid-sentence:



→ The next segment MUST NOT have a leading space.



Correct Examples:



- "Hello!" + " How are you?"

- "She turned," + " her voice trembling."



Incorrect Examples:



- "Hello!" + "How are you?"        (bad join, missing leading space)

- "Hello," + " my friend."         (bad join, extra leading space after comma)



=====================================================================

# 10. GEMINI PROMPTING BEST PRACTICES (APPLIED)

=====================================================================



You MUST follow:



- Clear task execution.

- Strict constraints.

- Deterministic output format.

- ALWAYS produce JSON with no commentary.

- NO creativity outside explicit instructions.

- ALL fields required, none extra.



You MUST treat:



- The section "OUTPUT FORMAT" as a binding contract.

- The few-shot example as a positive pattern (structure + style).

- The "JSON:" prefix as a required output anchor.



=====================================================================

# 11. FEW-SHOT POSITIVE EXAMPLE (DO NOT REUSE CONTENT)

=====================================================================



Example pattern (DO NOT REPEAT THIS IN THE REAL OUTPUT):



JSON:

[

  {{

    "speaker": "narrator",

    "original_text": "Once upon a time, three pigs left home.",

    "translated_text": "<emotion value='neutral' />Once upon a time, three pigs left home.",

    "voice_id": "some-uuid",

    "emotion": "neutral",

    "has_laughter": false,

    "needs_break": false,

    "scene_id": "scene_1"

  }}

]



You MUST use this pattern EXACTLY for:



- Overall JSON structure,

- Field names,

- Field order,

- General spacing style.



But you MUST NOT copy this example text or voice_id into the real output.



=====================================================================

# 12. AVAILABLE VOICES

=====================================================================



{self.voices_prompt}



You MUST choose "voice_id" values only from this voices list.



=====================================================================

# 13. TEXT TO ANALYZE

=====================================================================



{text}



=====================================================================

# FINAL INSTRUCTION

=====================================================================



Now produce the final output.



1. Output prefix MUST be exactly:



JSON:



2. Immediately after that, output ONLY the JSON array (no extra text).

3. The JSON array MUST follow all rules in this prompt.

"""

            # Generate content with retry logic for long responses
            max_retries = 3
            retry_count = 0
            
            while retry_count < max_retries:
                try:
                    logger.info(f"Calling Gemini API (attempt {retry_count + 1}/{max_retries})...")
                    response = self.gemini_model.generate_content(
                        prompt,
                        generation_config={
                            "temperature": 0.1,  # Lower temperature for more consistent JSON
                            "max_output_tokens": 65535,  # Increased to handle longer stories
                        }
                    )
                    try:
                        response_text = response.text.strip()
                    except (ValueError, AttributeError) as ve:
                        # Multi-part response or blocked response - access parts directly
                        if hasattr(response, 'candidates') and len(response.candidates) > 0:
                            candidate = response.candidates[0]
                            if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts') and len(candidate.content.parts) > 0:
                                response_text = candidate.content.parts[0].text.strip()
                            else:
                                logger.error(f"Gemini response has no content. Finish reason: {getattr(candidate, 'finish_reason', 'unknown')}")
                                if hasattr(candidate, 'safety_ratings'):
                                    logger.error(f"Safety ratings: {candidate.safety_ratings}")
                                raise ValueError("Gemini returned empty response - content may be blocked or filtered")
                        else:
                            logger.error(f"Gemini response structure unexpected: {response}")
                            raise ValueError("Gemini response has no candidates")
                    break
                except Exception as e:
                    is_timeout = ("timeout" in str(e).lower() or 
                                 "504" in str(e) or 
                                 "DeadlineExceeded" in str(type(e).__name__) or
                                 "timed out" in str(e).lower())
                    
                    retry_count += 1
                    if retry_count >= max_retries:
                        if is_timeout:
                            logger.error(f"Gemini API timed out after {max_retries} attempts")
                            raise ValueError(f"Gemini API request timed out after {max_retries} attempts. The model may be overloaded or the prompt is too complex. Try using 'gemini-2.5-pro' instead of 'gemini-2.5-pro' for faster responses.")
                        else:
                            logger.error(f"Gemini API call failed after {max_retries} attempts: {e}")
                            raise
                    
                    if is_timeout:
                        wait_time = min(2.0 * (2 ** retry_count), 30.0)  # Exponential backoff, max 30s
                        logger.warning(f"Request timed out. Retrying in {wait_time:.1f} seconds... (attempt {retry_count}/{max_retries})")
                    else:
                        wait_time = min(2.0 * (2 ** retry_count), 30.0)
                        logger.warning(f"API call failed: {e}. Retrying in {wait_time:.1f} seconds... (attempt {retry_count}/{max_retries})")
                    time.sleep(wait_time)

            def clean_json_response(text):
                cleaned = text.replace("```json", "").replace("```python", "").replace("```", "").strip()
                start_idx = cleaned.find('[')
                end_idx = cleaned.rfind(']')
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    cleaned = cleaned[start_idx:end_idx + 1]
                return cleaned.strip()

            def normalize_text_fields(segments):
                """Normalize text fields to remove line breaks and extra whitespace"""
                for segment in segments:
                    for field in ['original_text', 'translated_text']:
                        if field in segment and segment[field]:
                            text = str(segment[field])
                            text = text.replace('\n', ' ').replace('\r', ' ')
                            text = ' '.join(text.split())
                            segment[field] = text
                return segments

            try:
                return_text = json.loads(response_text)
            except json.JSONDecodeError as e:
                cleaned_text = clean_json_response(response_text)
                try:
                    return_text = json.loads(cleaned_text)
                except json.JSONDecodeError as e2:
                    error_msg = str(e2)
                    if "Unterminated string" in error_msg or "Expecting" in error_msg:
                        logger.error(f"JSON parsing error: {error_msg}")
                        logger.error(f"Response length: {len(response_text)} chars")
                        logger.error(f"Cleaned length: {len(cleaned_text)} chars")
                        try:
                            logger.warning("Attempting to recover partial JSON...")
                            bracket_count = 0
                            last_valid_pos = 0
                            for i, char in enumerate(cleaned_text):
                                if char == '[':
                                    bracket_count += 1
                                elif char == ']':
                                    bracket_count -= 1
                                    if bracket_count == 0:
                                        last_valid_pos = i + 1
                            if last_valid_pos > 0:
                                partial_json = cleaned_text[:last_valid_pos]
                                return_text = json.loads(partial_json)
                                logger.warning(f"Recovered {len(return_text)} segments from partial JSON")
                            else:
                                raise ValueError("Could not recover valid JSON")
                        except Exception as e3:
                            logger.error(f"Failed to parse Gemini response after cleaning")
                            logger.error(f"First 500 chars of response: {response_text[:500]}")
                            logger.error(f"Last 500 chars of response: {response_text[-500:]}")
                            raise ValueError(f"Failed to parse JSON response: {error_msg}. Response may be truncated.")
                    
            return_text = normalize_text_fields(return_text)

            # Process the returned JSON to use "translated_text" and add SSML tags
            processed_segments = []
            for segment in return_text:
                # Get emotion and laughter info (speed and volume removed - let text control naturally)
                emotion = segment.get("emotion", "neutral")
                has_laughter = segment.get("has_laughter", False)
                needs_break = segment.get("needs_break", False)
                
                if emotion not in self.primary_emotions:
                    logger.warning(f"Invalid emotion '{emotion}', defaulting to 'neutral'")
                    emotion = "neutral"
                
                text = segment.get("translated_text", segment.get("text", ""))
                
                if has_laughter and "[laughter]" not in text:
                    # Try to place laughter naturally - after exclamation or at end of sentence
                    if "!" in text:
                        text = text.replace("!", "! [laughter]", 1)
                    elif "." in text:
                        text = text.replace(".", ". [laughter]", 1)
                    else:
                        text = text + " [laughter]"
                
                # Build SSML-tagged text (emotion only, no speed/volume)
                ssml_text = ""
                if emotion and emotion != "neutral":
                    ssml_text += f'<emotion value="{emotion}" />'
                ssml_text += text
                
                # Add break tag only if explicitly needed (for dramatic pauses, scene changes, etc.)
                # Most segments should NOT have break tags - periods handle natural pauses
                if needs_break:
                    # Add a subtle break after the text (0.5-1s) for dramatic effect
                    # Only when the text explicitly suggests a longer pause
                    ssml_text += '<break time="0.8s" />'
                
                processed_segments.append({
                    "speaker": segment.get("speaker"),
                    "original_text": segment.get("original_text", ""),
                    "text": ssml_text,  # Use SSML-tagged text for TTS (emotion only, no speed/volume)
                    "voice_id": segment.get("voice_id"),
                    "emotion": emotion,
                    "has_laughter": has_laughter,
                    "scene_id": segment.get("scene_id", "scene_1")  # Default to scene_1 if missing
                })
            return processed_segments

        except Exception as e:
            logger.error(f"Error in Gemini API call: {str(e)}")
            raise

    async def generate_audio_group_websocket(self, segments_group: List[Dict], context_id: str) -> bytes:
        """
        Generates audio for a group of contiguous segments with the same voice.
        Maintains a single WebSocket connection for seamless prosody.
        Returns a single combined WAV byte object for the entire group.
        """
        try:
            if not segments_group:
                raise ValueError("Empty segment group provided")
                
            voice_id = segments_group[0]["voice_id"]
            language = segments_group[0].get("language", "en")
            
            ws_url = f"wss://api.cartesia.ai/tts/websocket?cartesia_version=2025-04-16&api_key={self.cartesia_api_key}"
            
            all_audio_bytes = bytearray()
            
            async with websockets.connect(ws_url) as websocket:
                # 1. Send all inputs rapidly
                for i, segment in enumerate(segments_group):
                    is_last = (i == len(segments_group) - 1)
                    text = segment["text"]
                    
                    request = {
                        "model_id": "sonic-3",
                        "voice": {"mode": "id", "id": voice_id},
                        "language": language,
                        "transcript": text,
                        "output_format": {
                            "container": "raw",
                            "sample_rate": self.sample_rate,
                            "encoding": "pcm_f32le",
                        },
                        "context_id": context_id,
                        "continue": not is_last, 
                        "max_buffer_delay_ms": 0,
                    }
                    await websocket.send(json.dumps(request))
                    logger.debug(f"Sent segment {i+1}/{len(segments_group)} to WS (continue={not is_last})")

                # 2. Receive all audio
                async for message in websocket:
                    if isinstance(message, (bytes, bytearray)):
                        all_audio_bytes.extend(message)
                        continue
                    
                    output = json.loads(message)
                    response_type = output.get("type", "unknown")
                    
                    if response_type == "done":
                        # The context is done (all segments finished)
                        break
                        
                    if response_type == "error":
                        error_msg = output.get("error", "Unknown error")
                        raise ValueError(f"Cartesia WebSocket error: {error_msg}")

                    if response_type == "chunk":
                        data_field = output.get("data")
                        if data_field:
                            try:
                                buffer = base64.b64decode(data_field)
                                all_audio_bytes.extend(buffer)
                            except Exception as e:
                                logger.warning(f"Error decoding audio chunk: {e}")
                                continue
            
            if not all_audio_bytes:
                 # It's possible for very short segments or errors to result in no audio
                 logger.warning("No audio received for group")
                 return b""

            # Convert raw PCM (float32) bytes into WAV bytes
            audio_array = np.frombuffer(all_audio_bytes, dtype=np.float32)
            
            with io.BytesIO() as wav_buffer:
                sf.write(wav_buffer, audio_array, self.sample_rate, format='WAV', subtype='PCM_16')
                wav_bytes = wav_buffer.getvalue()
                
            return wav_bytes

        except Exception as e:
            logger.error(f"Error in group generation: {e}")
            raise

    async def generate_audio_websocket_stream(self, text: str, voice_id: str, language: str, context_id: str, is_continuation: bool = False, has_more_segments: bool = False, emotions: List[str] = None):
        """
        Generate audio with streaming - yields raw PCM audio chunks as they arrive.
        
        This is an async generator that yields audio chunks in real-time for immediate playback.
        
        Args:
            text: Text to generate audio for (with SSML tags)
            voice_id: Cartesia voice ID
            language: Language code
            context_id: Unique context ID for continuations
            is_continuation: Whether this continues from previous audio
            has_more_segments: Whether more segments follow
            emotions: List of emotions (for compatibility)
        
        Yields:
            bytes: Raw PCM audio chunks (float32) as they arrive from the WebSocket
        """
        try:
            request = {
                "model_id": "sonic-3",
                "voice": {
                    "mode": "id",
                    "id": voice_id,
                },
                "language": language,
                "transcript": text,
                "output_format": {
                    "container": "raw",
                    "sample_rate": self.sample_rate,
                    "encoding": "pcm_f32le",
                },
                "max_buffer_delay_ms": 3000,
            }
            
            if not context_id or not isinstance(context_id, str) or len(context_id.strip()) == 0:
                raise ValueError(f"Invalid context_id: '{context_id}'. Must be a non-empty string.")
            
            request["context_id"] = context_id
            request["continue"] = is_continuation
            
            logger.debug(f"Streaming WebSocket request: context_id={context_id}, continue={is_continuation}")
            
            ws_url = f"wss://api.cartesia.ai/tts/websocket?cartesia_version=2025-04-16&api_key={self.cartesia_api_key}"
            
            async with websockets.connect(ws_url) as websocket:
                await websocket.send(json.dumps(request))
                
                async for message in websocket:
                    if isinstance(message, (bytes, bytearray)):
                        yield bytes(message)
                        continue

                    output = json.loads(message)
                    response_type = output.get("type", "unknown")

                    if response_type == "done":
                        break

                    if response_type == "error":
                        error_msg = output.get("error", "Unknown error")
                        raise ValueError(f"Cartesia WebSocket error: {error_msg}")

                    if response_type == "chunk":
                        data_field = output.get("data")
                        if data_field:
                            try:
                                buffer = base64.b64decode(data_field)
                                yield buffer
                            except Exception as e:
                                logger.warning(f"Error decoding audio chunk: {e}")
                                continue

                # Don't wait for flush here - let it happen in background
                # The audio is complete, flush is just cleanup

        except Exception as e:
            logger.error(f"Error in streaming audio generation: {str(e)}")
            raise

    async def flush_context(self, context_id: str):
        """
        Flush (finalize) a context after all audio is generated.
        This can be called in the background and doesn't affect audio playback.
        """
        try:
            ws_url = f"wss://api.cartesia.ai/tts/websocket?cartesia_version=2025-04-16&api_key={self.cartesia_api_key}"
            
            async with websockets.connect(ws_url) as websocket:
                flush_request = {
                    "context_id": context_id,
                    "flush": True
                }
                logger.debug(f"Flushing context {context_id} in background...")
                await websocket.send(json.dumps(flush_request))
                
                async for message in websocket:
                    if isinstance(message, str):
                        output = json.loads(message)
                        if output.get("type") == "done":
                            logger.debug(f"Context {context_id} flushed successfully")
                            break
        except Exception as e:
            logger.warning(f"Error flushing context (non-critical): {e}")

    async def generate_audio_websocket(self, text: str, voice_id: str, language: str, context_id: str, is_continuation: bool = False, has_more_segments: bool = False, emotions: List[str] = None) -> bytes:
        """
        Generate audio for a piece of text using Cartesia WebSocket API with sonic-3 model.
        The text parameter should contain SSML tags for emotion control only.
        Speed and volume are controlled naturally by the text content and punctuation.
        SSML format: <emotion value="emotion_name" />text content
        
        Uses continuations (context_id and continue flag) to maintain prosody between segments.
        
        Args:
            text: Text to generate audio for (with SSML tags)
            voice_id: Cartesia voice ID
            language: Language code
            context_id: Unique context ID for continuations
            is_continuation: Whether this continues from previous audio (False for first segment)
            has_more_segments: Whether more segments follow (affects flushing)
            emotions: List of emotions (for compatibility, not used)
        
        Returns WAV audio bytes.
        """
        try:
            # Create WebSocket request with continuation parameters
            request = {
                "model_id": "sonic-3",
                "voice": {
                    "mode": "id",
                    "id": voice_id,
                },
                "language": language,
                "transcript": text,  # Text includes SSML tags for emotion only
                "output_format": {
                    "container": "raw",
                    "sample_rate": self.sample_rate,
                    "encoding": "pcm_f32le",
                },
                # Don't buffer since we're sending complete sentences
                "max_buffer_delay_ms": 0,
            }
            
            # Add context_id for all requests (required for WebSocket API)
            # context_id is required even for the first segment to create the context
            # Ensure context_id is a valid string (not None or empty)
            if not context_id or not isinstance(context_id, str) or len(context_id.strip()) == 0:
                raise ValueError(f"Invalid context_id: '{context_id}'. Must be a non-empty string.")
            
            request["context_id"] = context_id
            
            # Set continue flag: False for first segment, True for all subsequent segments
            # This maintains prosody (rhythm/intonation) across segments
            request["continue"] = is_continuation
            
            logger.debug(
                f"WebSocket request: context_id={context_id}, continue={is_continuation}, has_more={has_more_segments}, text_length={len(text)}"
            )
            logger.debug(f"Full WebSocket request: {json.dumps(request, indent=2)}")
            
            ws_url = f"wss://api.cartesia.ai/tts/websocket?cartesia_version=2025-04-16&api_key={self.cartesia_api_key}"
            
            audio_bytes = bytearray()
            async with websockets.connect(ws_url) as websocket:
                request_json = json.dumps(request)
                logger.debug(f"Sending WebSocket request ({len(request_json)} chars)")
                await websocket.send(request_json)
                
                async for message in websocket:
                    # Cartesia may send binary frames containing raw PCM data
                    if isinstance(message, (bytes, bytearray)):
                        audio_bytes.extend(message)
                        logger.debug(f"Received binary audio chunk ({len(message)} bytes)")
                        continue

                    output = json.loads(message)
                    response_type = output.get("type", "unknown")

                    logger.debug(f"WebSocket response ({response_type}): {output}")

                    if response_type == "done":
                        break

                    if response_type == "error":
                        error_msg = output.get("error", "Unknown error")
                        raise ValueError(f"Cartesia WebSocket error: {error_msg}")

                    # Audio chunks have type="chunk" and contain base64-encoded data
                    if response_type == "chunk":
                        data_field = output.get("data")
                        if data_field:
                            try:
                                buffer = base64.b64decode(data_field)
                                audio_bytes.extend(buffer)
                                logger.debug(f"Decoded base64 audio chunk ({len(buffer)} bytes)")
                            except Exception as e:
                                logger.warning(f"Error decoding audio chunk: {e}")
                                continue
                        else:
                            logger.debug("Chunk response without data field")
                            continue

                # Skip flush - it's optional and takes too long
                # The audio is complete without it; flush is just cleanup

            if not audio_bytes:
                raise ValueError("No audio data received from Cartesia WebSocket")

            # Convert raw PCM (float32) bytes into WAV bytes
            audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
            if audio_array.size == 0:
                raise ValueError("Received empty audio data from Cartesia WebSocket")

            with io.BytesIO() as wav_buffer:
                sf.write(wav_buffer, audio_array, self.sample_rate, format='WAV', subtype='PCM_16')
                wav_bytes = wav_buffer.getvalue()

            logger.info(
                f"Generated audio for text segment (length: {len(text)} chars, raw: {len(audio_bytes)} bytes, wav: {len(wav_bytes)} bytes)"
            )
            return wav_bytes

        except Exception as e:
            logger.error(f"Error generating audio via WebSocket: {str(e)}")
            raise

    def generate_audio(self, text: str, voice_id: str, language: str, context_id: str, is_continuation: bool = False, has_more_segments: bool = False, emotions: List[str] = None) -> bytes:
        """
        Synchronous wrapper for async WebSocket audio generation.
        """
        return asyncio.run(
            self.generate_audio_websocket(text, voice_id, language, context_id, is_continuation, has_more_segments, emotions)
        )

    async def stream_audio_from_segments(self, segments_path: str, start_index: int = 0, output_path: str = None, audio_callback: Optional[Callable[[bytes], None]] = None) -> str:
        """
        Stream audio from segments.json starting at a specific index.
        Useful for resuming audio generation or streaming from any point.
        
        Args:
            segments_path: Path to segments.json file
            start_index: Index to start streaming from (0-based)
            output_path: Path to save final WAV file (optional)
            audio_callback: Optional callback for each audio chunk as it's generated
        
        Returns:
            Path to the final WAV file if output_path provided, otherwise None
        """
        try:
            # Load segments from JSON
            with open(segments_path, 'r', encoding='utf-8') as f:
                segments = json.load(f)
            
            if start_index >= len(segments):
                raise ValueError(f"Start index {start_index} is out of range. Total segments: {len(segments)}")
            
            logger.info(f"Streaming audio from segment {start_index + 1}/{len(segments)}")
            
            # Group segments to ensure seamless prosody
            # We only group segments starting from start_index
            segments_to_process = segments[start_index:]
            
            grouped_segments = []
            if segments_to_process:
                current_group = [segments_to_process[0]]
                for i in range(1, len(segments_to_process)):
                    segment = segments_to_process[i]
                    prev_segment = segments_to_process[i-1]
                    if segment["voice_id"] == prev_segment["voice_id"]:
                        current_group.append(segment)
                    else:
                        grouped_segments.append(current_group)
                        current_group = [segment]
                grouped_segments.append(current_group)
            
            logger.info(f"Grouped {len(segments_to_process)} segments into {len(grouped_segments)} voice groups")
            
            wav_chunks = []
            
            for group in grouped_segments:
                group_context_id = str(uuid.uuid4())
                
                speaker = group[0].get('speaker', 'unknown')
                logger.info(f"Generating audio for group: {speaker} ({len(group)} segments)")
                
                audio_bytes = await self.generate_audio_group_websocket(
                    segments_group=group,
                    context_id=group_context_id
                )
                
                wav_chunks.append(audio_bytes)
                
                if audio_callback:
                    audio_callback(audio_bytes)
            
            if output_path:
                logger.info("Concatenating audio chunks...")
                self.concatenate_wav_files(wav_chunks, output_path)
                logger.info(f"Audio streaming complete! Output: {output_path}")
                return output_path
            
            return None

        except Exception as e:
            logger.error(f"Error streaming audio from segments: {str(e)}")
            raise

    def process_book(
        self,
        pdf_path: str = None,
        output_dir: str = "output",
        language: str = "en",
        segments_json_path: str = None,
        book_id: str = None,
        audio_callback: Optional[Callable[[bytes], None]] = None,
    ) -> Dict[str, Optional[Union[str, bool]]]:
        """
        Process a PDF book and generate continuous audio output.
        Can load from MongoDB, existing segments.json, or process PDF with Gemini.

        Args:
            pdf_path: Path to PDF file (required if segments_json_path and book_id not provided)
            output_dir: Base output directory (default: "output")
            language: Language code (default: "en")
            segments_json_path: Path to existing segments.json (skips Gemini if provided)
            book_id: MongoDB book ID to load segments from (e.g., "three_little_pigs")
            audio_callback: Optional callback for audio chunks

        Returns a dictionary with:
            success: bool - True if audio generation succeeded
            segments_json: str | None - Path to segments JSON (if generated)
            final_wav: str | None - Path to final WAV file (if generated)
            error: str | None - Error message if generation failed
        """
        try:
            # Determine source: MongoDB, segments.json, or PDF
            if book_id:
                logger.info(f"Loading segments from MongoDB for book: {book_id}")
                segments_with_voices = self.fetch_segments_from_mongodb(book_id)
                
                pdf_output_folder = os.path.join(output_dir, book_id)
                os.makedirs(pdf_output_folder, exist_ok=True)
                
                json_output_path = os.path.join(pdf_output_folder, "segments.json")
                with open(json_output_path, 'w', encoding='utf-8') as f:
                    json.dump(segments_with_voices, f, indent=2, ensure_ascii=False)
                logger.info(f"Saved segments from MongoDB to: {json_output_path}")
                
            elif segments_json_path:
                logger.info(f"Loading segments from: {segments_json_path}")
                with open(segments_json_path, 'r', encoding='utf-8') as f:
                    segments_with_voices = json.load(f)
                logger.info(f"Loaded {len(segments_with_voices)} segments from JSON")
                
                pdf_output_folder = os.path.dirname(segments_json_path)
                json_output_path = segments_json_path
                
            else:
                if not pdf_path:
                    raise ValueError("Either pdf_path or segments_json_path must be provided")
                
                os.makedirs(output_dir, exist_ok=True)
                
                pdf_basename = os.path.basename(pdf_path)
                pdf_name_without_ext = os.path.splitext(pdf_basename)[0]
                
                pdf_output_folder = os.path.join(output_dir, pdf_name_without_ext)
                os.makedirs(pdf_output_folder, exist_ok=True)
                logger.info(f"Created output folder: {pdf_output_folder}")
                
                logger.info(f"Extracting text from PDF: {pdf_path}")
                text = self.extract_text_from_pdf(pdf_path)
                logger.info(f"Extracted {len(text)} characters from PDF")
                
                # Normalize text - remove excessive line breaks before processing
                # This helps prevent Gemini from inserting \n characters
                text = ' '.join(text.split())
                
                # For very long texts, we might need to chunk them
                # But first try processing the whole text
                max_text_length = 8000  # Reasonable limit to avoid token issues
                if len(text) > max_text_length:
                    logger.warning(f"Text is very long ({len(text)} chars). Processing in chunks may be needed if Gemini fails.")
                
                logger.info("Analyzing text and assigning voices with Gemini...")
                segments_with_voices = self.analyze_text_and_assign_voices_with_gemini(text, language=language)
                logger.info(f"Processed {len(segments_with_voices)} segments")
                
                json_output_path = os.path.join(pdf_output_folder, "segments.json")
                with open(json_output_path, 'w', encoding='utf-8') as f:
                    json.dump(segments_with_voices, f, indent=2, ensure_ascii=False)
                logger.info(f"Saved segments JSON to: {json_output_path}")
            
            result: Dict[str, Optional[str]] = {
                "success": False,
                "segments_json": json_output_path,
                "final_wav": None,
                "error": None,
            }
            
            # Group segments by voice_id to ensure seamless prosody within a character's speech
            grouped_segments = []
            if segments_with_voices:
                current_group = [segments_with_voices[0]]
                
                for i in range(1, len(segments_with_voices)):
                    segment = segments_with_voices[i]
                    prev_segment = segments_with_voices[i-1]
                    
                    # Check if voice matches the current group
                    if segment["voice_id"] == prev_segment["voice_id"]:
                        current_group.append(segment)
                    else:
                        # Voice changed, save group and start new one
                        grouped_segments.append(current_group)
                        current_group = [segment]
                
                grouped_segments.append(current_group)
            
            logger.info(f"Grouped {len(segments_with_voices)} segments into {len(grouped_segments)} voice groups for seamless prosody")

            # Generate audio for each group
            wav_chunks = []
            segment_timings = []  # Track timing for each segment
            cumulative_time = 0.0  # Track cumulative time in seconds
            processed_count = 0
            
            for group_idx, group in enumerate(grouped_segments):
                voice_id = group[0]["voice_id"]
                speaker = group[0].get("speaker", "unknown")
                
                # Generate a unique context_id for this specific group of continuous speech
                # This ensures we don't mix contexts between voices
                group_context_id = str(uuid.uuid4())
                
                logger.info(f"Processing group {group_idx+1}/{len(grouped_segments)}: {speaker} ({len(group)} segments)")
                
                try:
                    # Call the group generation method (using asyncio.run to bridge sync/async)
                    audio_bytes = asyncio.run(self.generate_audio_group_websocket(group, group_context_id))
                    
                    wav_chunks.append(audio_bytes)
                    
                    # Calculate duration of the group audio
                    with io.BytesIO(audio_bytes) as wav_io:
                        audio_data, sample_rate = sf.read(wav_io, dtype='float32')
                        num_samples = len(audio_data)
                        duration = num_samples / sample_rate
                    
                    # Distribute duration among the segments in the group proportionally based on text length
                    total_chars = sum(len(s["text"]) for s in group)
                    group_start_time = cumulative_time
                    
                    for seg in group:
                        seg_len = len(seg["text"])
                        # Proportional duration (estimate, but seamless audio makes exact boundaries less critical for playback)
                        seg_duration = (seg_len / total_chars) * duration if total_chars > 0 else 0
                        
                        timing_info = {
                            "segment_index": processed_count,
                            "speaker": seg.get("speaker", "unknown"),
                            "text": seg.get("original_text", ""),
                            "start_time": cumulative_time,
                            "duration": seg_duration,
                            "end_time": cumulative_time + seg_duration
                        }
                        segment_timings.append(timing_info)
                        
                        logger.info(
                            f"  ⏱️  Segment {processed_count+1} timing: start={cumulative_time:.2f}s, duration={seg_duration:.2f}s"
                        )
                        
                        cumulative_time += seg_duration
                        processed_count += 1
                    
                    if audio_callback:
                        audio_callback(audio_bytes)
                        
                except Exception as segment_error:
                    error_message = f"Group {group_idx+1} ({speaker}): {segment_error}"
                    logger.error(f"Audio generation failed: {error_message}")
                    result["error"] = error_message
                    break
            
            try:
                if result["error"]:
                    logger.error(f"Audio generation aborted due to error: {result['error']}")
                    logger.info(f"Segments JSON saved to: {json_output_path}")
                    return result

                # Save timing information to a separate JSON file
                timing_output_path = os.path.join(pdf_output_folder, "segment_timings.json")
                timing_data = {
                    "total_duration": cumulative_time,
                    "total_segments": len(segment_timings),
                    "segments": segment_timings
                }
                with open(timing_output_path, 'w', encoding='utf-8') as f:
                    json.dump(timing_data, f, indent=2, ensure_ascii=False)
                logger.info(f"📊 Segment timings saved to: {timing_output_path}")
                logger.info(f"📊 Total audiobook duration: {cumulative_time:.2f} seconds ({cumulative_time/60:.2f} minutes)")

                logger.info("Concatenating audio chunks...")
                final_wav_file = os.path.join(pdf_output_folder, "book_continuous.wav")
                self.concatenate_wav_files(wav_chunks, final_wav_file)
                
                logger.info(f"Audio generation complete! Output: {final_wav_file}")
                logger.info(f"Segments JSON saved to: {json_output_path}")
                result["success"] = True
                result["final_wav"] = final_wav_file
                result["timing_json"] = timing_output_path
                return result
            except Exception as audio_error:
                error_message = str(audio_error)
                logger.error(f"Audio generation failed: {error_message}")
                logger.info(f"Segments JSON saved to: {json_output_path}")
                result["error"] = error_message
                return result

        except Exception as e:
            logger.error(f"Error processing book: {str(e)}")
            raise

    @staticmethod
    def concatenate_wav_files(wav_chunks: List[bytes], output_path: str):
        """
        Concatenate multiple WAV file chunks into a single WAV file.
        Uses soundfile to handle extended WAV formats (like pcm_f32le).
        """
        try:
            all_audio_data = []
            sample_rate = None
            num_channels = None
            
            # Read all WAV chunks and extract audio data using soundfile
            # (handles extended WAV formats that wave module can't)
            for chunk in wav_chunks:
                with io.BytesIO(chunk) as chunk_io:
                    # Use soundfile to read WAV (handles extended formats)
                    data, sr = sf.read(chunk_io, dtype='float32')
                    
                    if sample_rate is None:
                        sample_rate = sr
                        num_channels = 1 if len(data.shape) == 1 else data.shape[1]
                    else:
                        if sr != sample_rate:
                            logger.warning(f"WAV chunk sample rate mismatch ({sr} vs {sample_rate}), skipping...")
                            continue
                        chunk_channels = 1 if len(data.shape) == 1 else data.shape[1]
                        if chunk_channels != num_channels:
                            logger.warning(f"WAV chunk channel mismatch ({chunk_channels} vs {num_channels}), skipping...")
                            continue
                    
                    if len(data.shape) == 1:
                        data = data.reshape(-1, 1)
                    
                    all_audio_data.append(data)
            
            if not all_audio_data:
                raise ValueError("No valid audio data to concatenate")
            
            concatenated_audio = np.concatenate(all_audio_data, axis=0)
            
            # Write the final WAV file using soundfile
            # Convert to mono if needed, otherwise keep as stereo
            if num_channels == 1:
                concatenated_audio = concatenated_audio.flatten()
            
            sf.write(output_path, concatenated_audio, sample_rate, format='WAV', subtype='PCM_16')
            
            logger.info(f"Concatenated {len(wav_chunks)} WAV chunks into {output_path}")

        except Exception as e:
            logger.error(f"Error concatenating WAV files: {e}")
            raise

    def cleanup(self):
        """Cleanup resources before exit."""
        try:
            if hasattr(self, 'gemini_model'):
                del self.gemini_model
            if hasattr(self, 'cartesia_client'):
                pass
            if hasattr(self, 'mongo_client') and self.mongo_client is not None:
                self.mongo_client.close()
                logger.info("MongoDB connection closed")
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")

if __name__ == "__main__":
    import sys
    import argparse
    
    load_dotenv()
    
    parser = argparse.ArgumentParser(description="Generate audiobooks from PDFs, MongoDB, or existing segments.json")
    parser.add_argument("--pdf", type=str, help="Path to PDF file")
    parser.add_argument("--segments-json", type=str, help="Path to existing segments.json (skips Gemini processing)")
    parser.add_argument("--book-id", type=str, help="MongoDB book ID to load segments from (e.g., 'three_little_pigs')")
    parser.add_argument("--output", type=str, default="output", help="Output directory (default: output)")
    parser.add_argument("--language", type=str, default="en", help="Language code (default: en)")
    
    # Support old command-line format for backward compatibility
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        # Old format: python audio_reader.py [pdf_path] [output_dir] [language]
        pdf_path = sys.argv[1]
        output_dir = sys.argv[2] if len(sys.argv) > 2 else "output"
        language = sys.argv[3] if len(sys.argv) > 3 else "en"
        segments_json_path = None
        book_id = None
    else:
        args = parser.parse_args()
        pdf_path = args.pdf
        segments_json_path = args.segments_json
        book_id = args.book_id
        output_dir = args.output
        language = args.language
        
        if not pdf_path and not segments_json_path and not book_id:
            pdf_path = "/Users/ansh_is_g/Documents/cs348-project/audio_reader_standalone/The Tortoise and the Hare.pdf"
    
    try:
        logger.info("=" * 60)
        logger.info("Starting audiobook generation with Cartesia SDK")
        logger.info("=" * 60)
        if book_id:
            logger.info(f"Loading from MongoDB book ID: {book_id}")
        elif segments_json_path:
            logger.info(f"Loading from segments.json: {segments_json_path}")
        else:
            logger.info(f"PDF: {pdf_path}")
        logger.info(f"Output directory: {output_dir}")
        logger.info(f"Language: {language}")
        logger.info("=" * 60)
        
        reader = AudiobookReaderContinuous()
        
        # Optional callback for processing audio chunks as they're generated
        def progress_callback(audio_chunk: bytes):
            logger.debug(f"Generated audio chunk: {len(audio_chunk)} bytes")
        
        result = reader.process_book(
            pdf_path=pdf_path,
            output_dir=output_dir,
            language=language,
            segments_json_path=segments_json_path,
            book_id=book_id,
            audio_callback=progress_callback
        )
        
        if result["success"]:
            final_wav_path = result["final_wav"]
            logger.info("=" * 60)
            logger.info(f"✅ SUCCESS! Audiobook generated: {final_wav_path}")
            logger.info(f"📄 Segments JSON: {result['segments_json']}")
            logger.info("=" * 60)
        else:
            logger.error("=" * 60)
            logger.error("❌ AUDIO GENERATION FAILED")
            logger.error(f"Reason: {result['error']}")
            logger.error("=" * 60)
            if result["segments_json"]:
                logger.info(f"Segments JSON available at: {result['segments_json']}")
            sys.exit(1)
        
    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"❌ ERROR: {e}")
        logger.error("=" * 60)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if 'reader' in locals():
            reader.cleanup()
