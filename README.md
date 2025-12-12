# Audiobook Application - Ansh Gangapurkar - CS348

A MERN stack application that converts PDFs into AI-narrated audiobooks with synchronized text highlighting.

## Features

- **PDF to Audiobook**: Upload PDFs, generate multi-voice audio using Gemini AI + Cartesia TTS
- **Synchronized Playback**: Click any sentence to jump; active text highlights as audio plays
- **Real-time Progress**: Live updates during processing via Server-Sent Events

## Tech Stack

- **Frontend**: React 18, Vite, Tailwind CSS
- **Backend**: Node.js, Express, MongoDB
- **AI**: Gemini (text analysis), Cartesia (voice synthesis)

## Quick Start

### Prerequisites

- Node.js 18+
- MongoDB
- Python 3.10+
- API Keys: [Gemini](https://ai.google.dev/) and [Cartesia](https://cartesia.ai/)

### Setup

```bash
# 1. Start MongoDB
brew services start mongodb-community

# 2. Configure API keys
cp audio_reader_standalone/env_template.txt audio_reader_standalone/.env
# Edit .env with your GOOGLE_API_KEY and CARTESIA_API_KEY

# 3. Start everything
./start-dev.sh
```

Open http://localhost:3000

### Clean Start

```bash
./start-dev.sh --clean
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/books` | List all books |
| POST | `/api/books/upload` | Upload PDF |
| GET | `/api/books/:id/segments` | Get segments with timing |
| GET | `/api/books/:id/audio` | Stream audio |
| DELETE | `/api/books/:id` | Delete book |

## Keyboard Shortcuts

- `Space` - Play/Pause
- `←` `→` - Previous/Next sentence

## License

MIT - CS348 Course Project
