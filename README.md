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
cp backend/audio_reader_standalone/env_template.txt backend/audio_reader_standalone/.env
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

## Deployment

### Backend (Railway)

Uses Docker to run both Node.js and Python (for audio generation).

1. Create a new project on [Railway](https://railway.app/)
2. Connect your GitHub repo and set `backend` as the root directory
3. Railway will auto-detect the `Dockerfile`
4. Set environment variables:
   - `MONGO_URI` - MongoDB Atlas connection string
   - `MONGO_DB_NAME` - Database name (default: `audiobooks_db`)
   - `FRONTEND_URL` - Your Vercel URL (for CORS)
   - `GOOGLE_API_KEY` - Gemini API key (for text analysis)
   - `CARTESIA_API_KEY` - Cartesia API key (for TTS)
5. Deploy

### Frontend (Vercel)

1. Create a new project on [Vercel](https://vercel.com/)
2. Connect your GitHub repo and set `frontend` as root directory
3. Set environment variable:
   - `VITE_API_URL` - Your Railway backend URL (e.g., `https://your-app.up.railway.app`)
4. Deploy

### Environment Variables Summary

| Service | Variable | Description |
|---------|----------|-------------|
| Railway | `MONGO_URI` | MongoDB Atlas connection string |
| Railway | `MONGO_DB_NAME` | Database name |
| Railway | `FRONTEND_URL` | Vercel URL (for CORS) |
| Railway | `GOOGLE_API_KEY` | Gemini API key |
| Railway | `CARTESIA_API_KEY` | Cartesia TTS API key |
| Vercel | `VITE_API_URL` | Railway backend URL |

## License

MIT - CS348 Course Project
