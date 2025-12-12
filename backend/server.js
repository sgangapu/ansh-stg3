const express = require('express');
const cors = require('cors');
const path = require('path');
const { MongoClient } = require('mongodb');
require('dotenv').config();

const booksRouter = require('./routes/books');
const { importExistingBooks } = require('./services/bookImporter');

const app = express();
const PORT = process.env.PORT || 5000;
const MONGO_URI = process.env.MONGO_URI || 'mongodb://localhost:27017/';
const MONGO_DB_NAME = process.env.MONGO_DB_NAME || 'audiobooks_db';

// MongoDB connection
let db;
let mongoClient;

/**
 * Connect to MongoDB and return the database instance
 */
async function connectToMongoDB() {
  try {
    mongoClient = new MongoClient(MONGO_URI);
    await mongoClient.connect();
    db = mongoClient.db(MONGO_DB_NAME);
    console.log(`✅ Connected to MongoDB: ${MONGO_DB_NAME}`);
    return db;
  } catch (error) {
    console.error('❌ MongoDB connection error:', error);
    process.exit(1);
  }
}

// #STAGE3-B: DATABASE INDEXES
async function createIndexes() {
  console.log('📇 Creating/verifying database indexes...');
  
  try {
    // #STAGE3-B Index 1: book_id (unique) - for GET /api/books/:bookId
    await db.collection('books').createIndex(
      { book_id: 1 },
      { unique: true, name: 'idx_books_book_id' }
    );
    
    // #STAGE3-B Index 2: title - for GET /api/books?title=... (regex search)
    await db.collection('books').createIndex(
      { title: 1 },
      { name: 'idx_books_title' }
    );
    
    // #STAGE3-B Index 3: duration - for GET /api/books?minDuration=X&maxDuration=Y
    await db.collection('books').createIndex(
      { duration: 1 },
      { name: 'idx_books_duration' }
    );
    
    // #STAGE3-B Index 4: created_at (desc) - for sorting and date range queries
    await db.collection('books').createIndex(
      { created_at: -1 },
      { name: 'idx_books_created_at' }
    );
    
    // #STAGE3-B Index 5: (book_id, segment_index) - for GET /api/books/:bookId/segments
    await db.collection('segment_timings').createIndex(
      { book_id: 1, segment_index: 1 },
      { unique: true, name: 'idx_timings_book_segment' }
    );
    
    // #STAGE3-B Index 6: (book_id, start_time) - for find_segment_at_time() audio sync
    await db.collection('segment_timings').createIndex(
      { book_id: 1, start_time: 1 },
      { name: 'idx_timings_book_start_time' }
    );
    
    // #STAGE3-B Index 7: (book_id, speaker) - for GET /api/books/:bookId/speaker-stats report
    await db.collection('segment_timings').createIndex(
      { book_id: 1, speaker: 1 },
      { name: 'idx_timings_book_speaker' }
    );
    
    // #STAGE3-B Index 8: (book_id, segment_index) for segments collection
    await db.collection('segments').createIndex(
      { book_id: 1, segment_index: 1 },
      { unique: true, name: 'idx_segments_book_segment' }
    );
    
    console.log('✅ All indexes created/verified');
    
  } catch (error) {
    console.error('⚠️  Index creation warning:', error.message);
    // Don't fail startup if indexes already exist with different options
  }
}

/**
 * Get the MongoDB client for transaction support
 * Exported so routes can create sessions for multi-document transactions
 */
function getMongoClient() {
  return mongoClient;
}

// CORS configuration for production
const allowedOrigins = [
  'https://ansh-stg3.vercel.app',
  'http://localhost:3000'
];

// Add FRONTEND_URL env var if set
if (process.env.FRONTEND_URL) {
  allowedOrigins.push(process.env.FRONTEND_URL);
}

const corsOptions = {
  origin: allowedOrigins,
  credentials: true
};

// Middleware
app.use(cors(corsOptions));
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Static file serving for audio files
const audioOutputPath = path.join(__dirname, '../audio_reader_standalone/output');
app.use('/audio', express.static(audioOutputPath));

// Make db and mongoClient available to routes
// mongoClient is needed for transaction support (creating sessions)
app.use((req, res, next) => {
  req.db = db;
  req.mongoClient = mongoClient;  // For transaction sessions
  next();
});

// Routes
app.use('/api/books', booksRouter);

// Health check
app.get('/api/health', (req, res) => {
  res.json({
    status: 'ok',
    mongodb: db ? 'connected' : 'disconnected',
    timestamp: new Date().toISOString()
  });
});

// Error handling middleware
app.use((err, req, res, next) => {
  console.error('Error:', err);
  res.status(err.status || 500).json({
    error: err.message || 'Internal server error',
    ...(process.env.NODE_ENV === 'development' && { stack: err.stack })
  });
});

// Start server
async function startServer() {
  await connectToMongoDB();
  
  // Create indexes for efficient queries
  await createIndexes();

  // Import existing books on startup
  console.log('📚 Checking for existing audiobooks...');
  await importExistingBooks(db);

  app.listen(PORT, () => {
    console.log(`🚀 Server running on http://localhost:${PORT}`);
    console.log(`📁 Audio files served from: ${audioOutputPath}`);
  });
}

// Graceful shutdown
process.on('SIGINT', async () => {
  console.log('\n🛑 Shutting down gracefully...');
  if (mongoClient) {
    await mongoClient.close();
    console.log('📊 MongoDB connection closed');
  }
  process.exit(0);
});

startServer();

module.exports = { app, getMongoClient };

