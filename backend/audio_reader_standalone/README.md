# 🎵 AI Audiobook Generation Pipeline

Complete pipeline for generating multi-voice audiobooks from PDFs using Gemini AI and Cartesia TTS, with MongoDB storage and timing data for playback control.

## 🚀 Quick Start

### Prerequisites

1. **Python 3.10+** with virtual environment
2. **MongoDB** (local or cloud)
3. **API Keys**:
   - Gemini API key (for text analysis)
   - Cartesia API key (for voice synthesis)

### Setup

```bash
# 1. Install dependencies
cd audio_reader_standalone
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements_mongo.txt

# 2. Create .env file with your API keys
cat > .env << EOF
GOOGLE_API_KEY=your_gemini_api_key_here
CARTESIA_API_KEY=your_cartesia_api_key_here
MONGO_URI=mongodb://localhost:27017/
MONGO_DB_NAME=audiobooks_db
EOF

# 3. Start MongoDB (if not already running)
brew services start mongodb-community
# OR with Docker:
# docker run -d -p 27017:27017 --name mongodb mongo:latest
```

### Generate Your First Audiobook

```bash
# Run the complete pipeline with one command
./run_complete_pipeline.sh "The Tortoise and the Hare.pdf"
```

That's it! The script will:
1. ✅ Analyze the PDF with Gemini AI
2. ✅ Import segments to MongoDB
3. ✅ Generate multi-voice audio with Cartesia
4. ✅ Create timing data for playback control
5. ✅ Import timing data to MongoDB

## 📊 Pipeline Overview

```
PDF File
   ↓
[Gemini AI] ← Analyzes text, identifies characters, assigns voices
   ↓
segments.json
   ↓
[MongoDB] ← Stores segments
   ↓
[Cartesia TTS] ← Generates audio with multiple voices
   ↓
book_continuous.wav + segment_timings.json
   ↓
[MongoDB] ← Stores timing data for playback control
```

## 📁 File Structure

### Core Pipeline Files

```
audio_reader_standalone/
├── audio_reader.py              # Main audiobook generation engine
├── generate_segments.py         # Step 1: PDF → segments.json
├── mongo_service.py            # Step 2: segments → MongoDB
├── timing_service.py           # Step 4: timing → MongoDB
├── run_complete_pipeline.sh    # One-command pipeline runner
├── requirements.txt            # Python dependencies
├── requirements_mongo.txt      # MongoDB dependencies
└── .env                        # API keys (create this)
```

### Documentation

```
├── TIMING_README.md            # Timing system documentation
└── timing_example.py           # Working code examples
```

### Input/Output

```
├── *.pdf                       # Input PDF files
└── output/
    └── book_id/
        ├── segments.json           # Analyzed text segments
        ├── segment_timings.json    # Audio timing data
        └── book_continuous.wav     # Final audiobook
```

## 🔧 Individual Commands

If you want to run steps individually instead of using the pipeline script:

### Step 1: Generate Segments

```bash
python generate_segments.py "path/to/book.pdf"
# Output: output/book_name/segments.json
```

### Step 2: Import Segments to MongoDB

```bash
python mongo_service.py import "output/book_name/segments.json" --title "Book Name"
# Creates MongoDB collection: segments
```

### Step 3: Generate Audio with Timing

```bash
python audio_reader.py --book-id "book_id"
# Output:
#   - output/book_id/book_continuous.wav
#   - output/book_id/segment_timings.json
```

### Step 4: Import Timing Data

```bash
python timing_service.py import "output/book_id/segment_timings.json" book_id
# Creates MongoDB collection: segment_timings
```

## 📚 MongoDB Collections

### Collection: `books`
Stores book metadata.

```javascript
{
  book_id: "the_tortoise_and_the_hare",
  title: "The Tortoise and the Hare",
  total_segments: 45,
  created_at: ISODate("2025-11-12T...")
}
```

### Collection: `segments`
Stores text segments with voice assignments.

```javascript
{
  book_id: "the_tortoise_and_the_hare",
  segment_index: 0,
  speaker: "Narrator",
  original_text: "Once upon a time...",
  translated_text: "<emotion value='neutral' />Once upon a time...",
  voice_id: "ed82c17b-4704-4d34-be43-5d19065acdf1",
  emotion: "neutral"
}
```

### Collection: `segment_timings`
Stores audio timing data for playback control.

```javascript
{
  book_id: "the_tortoise_and_the_hare",
  segment_index: 0,
  speaker: "Narrator",
  text: "Once upon a time...",
  start_time: 0.0,      // seconds from start
  duration: 3.45,        // segment duration
  end_time: 3.45        // when segment ends
}
```

## 🎯 Use Cases

### Query Timing Data

```bash
# Get timing for a specific segment
python timing_service.py get the_tortoise_and_the_hare 15

# Find what's playing at 45.5 seconds
python timing_service.py find the_tortoise_and_the_hare 45.5

# Search for segments containing "tortoise"
python timing_service.py search the_tortoise_and_the_hare tortoise

# Get total duration
python timing_service.py duration the_tortoise_and_the_hare
```

### In Your Application

```python
from timing_service import TimingService

service = TimingService()

# User clicks "Skip to segment 15"
timing = service.get_segment_timing("the_tortoise_and_the_hare", 15)
audio_player.seek(timing['start_time'])  # Jump to that timestamp

# User scrubs timeline to 45.5 seconds
timing = service.find_segment_at_time("the_tortoise_and_the_hare", 45.5)
display_text(timing['text'])
```

## 🎨 Features

- **Multi-Voice Generation**: Gemini AI analyzes text and assigns appropriate voices to different characters
- **Emotion Detection**: Automatically detects emotions and applies appropriate voice modulation
- **Voice Consistency**: Same character always uses the same voice throughout the book
- **Prosody Continuity**: Smooth transitions between segments for natural flow
- **Timing Data**: Precise timing information for each segment enables:
  - Skip to segment
  - Timeline scrubbing
  - Progress tracking
  - Text highlighting sync
  - Search and jump to text

## 📖 Documentation

- **Main README**: This file
- **Timing System**: See `TIMING_README.md`
- **Examples**: Run `python timing_example.py`

## 🛠️ Troubleshooting

### MongoDB Connection Error

```bash
# Make sure MongoDB is running
brew services list | grep mongodb

# If not, start it:
brew services start mongodb-community
```

### API Key Issues

Make sure your `.env` file exists and contains valid API keys:

```bash
cat .env
# Should show:
# GOOGLE_API_KEY=...
# CARTESIA_API_KEY=...
```

### Audio Generation Slow

The audio generation can take several minutes depending on:
- Story length
- Number of segments
- Cartesia API response time

Progress is logged in real-time so you can monitor it.

### Old Outputs Conflicting

Clean old outputs:

```bash
rm -rf output/old_book_name
```

## 📊 Performance

Typical performance for a short story (2-3 pages):
- **Segment Generation**: 30-60 seconds (Gemini AI)
- **Audio Generation**: 3-5 minutes (depends on length)
- **MongoDB Import**: < 1 second

## 🔑 Environment Variables

```bash
GOOGLE_API_KEY         # Gemini API key for text analysis
CARTESIA_API_KEY       # Cartesia API key for voice synthesis
MONGO_URI              # MongoDB connection string (default: mongodb://localhost:27017/)
MONGO_DB_NAME          # Database name (default: audiobooks_db)
LOG_LEVEL              # Logging level (default: INFO)
```

## 🎵 Output Files

Each audiobook generates:

1. **segments.json** - Analyzed text with voice assignments
2. **book_continuous.wav** - Final audio file (44.1kHz, mono, PCM 16-bit)
3. **segment_timings.json** - Timing data for playback control

## 🚧 Limitations

- **English only**: Currently optimized for English voices and text
- **PDF format**: Input must be PDF (extractable text, not scanned images)
- **Story length**: Very long books may need to be split
- **Rate limits**: Free tier APIs have rate limits (Gemini: 15 req/min, Cartesia varies)

## 📝 License

[Your license here]

## 🤝 Contributing

[Your contribution guidelines here]

## 📞 Support

For issues or questions:
1. Check the documentation in `TIMING_README.md`
2. Review examples in `timing_example.py`
3. Check MongoDB connection
4. Verify API keys are valid

