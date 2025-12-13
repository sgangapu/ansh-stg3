const express = require('express');
const router = express.Router();
const multer = require('multer');
const path = require('path');
const fs = require('fs').promises;
const {
  processAudiobook,
  getStatus,
  registerSSEListener,
  generateBookId
} = require('../services/audiobookPipeline');

const {
  validateBookIdParam,
  validateBookBody,
  validateBookQueryParams,
  validateBookId,
  validateStringInput
} = require('../utils/validation');

// Configure Multer for file uploads
const storage = multer.diskStorage({
  destination: async (req, file, cb) => {
    const uploadDir = path.join(__dirname, '../uploads');
    try {
      await fs.mkdir(uploadDir, { recursive: true });
      cb(null, uploadDir);
    } catch (error) {
      cb(error);
    }
  },
  filename: (req, file, cb) => {
    // Sanitize filename
    const sanitized = file.originalname.replace(/[^a-zA-Z0-9._-]/g, '_');
    const timestamp = Date.now();
    cb(null, `${timestamp}_${sanitized}`);
  }
});

const upload = multer({
  storage,
  limits: {
    fileSize: 50 * 1024 * 1024 // 50MB max
  },
  fileFilter: (req, file, cb) => {
    if (file.mimetype === 'application/pdf') {
      cb(null, true);
    } else {
      cb(new Error('Only PDF files are allowed'), false);
    }
  }
});

/**
 * POST /api/books
 * Body: { title: string, duration?: number, total_segments?: number }
 * INSERT REQUIREMENT
 * 
 * SECURITY: validateBookBody middleware sanitizes title input to prevent NoSQL injection
 */
router.post('/', validateBookBody, async (req, res) => {
  try {
    const { title, duration, total_segments } = req.body;
    const db = req.db;

    // Validation: title is required and already sanitized by middleware
    if (!title || title.trim().length === 0) {
      return res.status(400).json({ error: 'Title is required' });
    }

    // Generate book_id from title (generateBookId already sanitizes)
    const bookId = generateBookId(title);

    // SECURITY: Using parameterized query - bookId is passed as a value, not concatenated
    // This is safe because MongoDB driver treats it as a literal value, not an operator
    // Example of UNSAFE code: db.collection('books').find(`{book_id: "${bookId}"}`) 
    // Example of SAFE code (what we use): db.collection('books').findOne({ book_id: bookId })
    const existingBook = await db.collection('books').findOne({ book_id: bookId });
    if (existingBook) {
      return res.status(409).json({ error: 'Book with this title already exists' });
    }

    // Create new book with sanitized inputs
    const newBook = {
      book_id: bookId,
      title: title.trim(),
      duration: duration || 0,
      total_segments: total_segments || 0,
      created_at: new Date(),
      updated_at: new Date()
    };

    const result = await db.collection('books').insertOne(newBook);

    res.status(201).json({
      message: 'Book created successfully',
      book: newBook
    });

  } catch (error) {
    console.error('Error creating book:', error);
    res.status(500).json({ error: error.message });
  }
});

/**
 * POST /api/books/upload
 * Upload a PDF and start processing pipeline
 */
router.post('/upload', upload.single('pdf'), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: 'No PDF file uploaded' });
    }

    const { originalname, path: filePath } = req.file;
    const title = req.body.title || path.parse(originalname).name;
    const bookId = generateBookId(title);

    console.log(`📤 Upload received: ${originalname}`);
    console.log(`📖 Title: ${title}`);
    console.log(`🆔 Book ID: ${bookId}`);

    // Start processing in background
    processAudiobook(filePath, title)
      .then(async () => {
        // Clean up uploaded PDF after successful processing
        try {
          await fs.unlink(filePath);
          console.log(`🗑️  Cleaned up temporary file: ${filePath}`);
        } catch (error) {
          console.error(`Failed to delete temp file: ${error.message}`);
        }
      })
      .catch(async (error) => {
        console.error(`Pipeline failed for ${bookId}:`, error);
        // Clean up on error too
        try {
          await fs.unlink(filePath);
        } catch { }
      });

    res.json({
      bookId,
      title,
      status: 'processing',
      message: 'Upload successful. Processing started.'
    });

  } catch (error) {
    console.error('Upload error:', error);
    res.status(500).json({ error: error.message });
  }
});

/**
 * GET /api/books/:bookId/status
 * Server-Sent Events stream for real-time processing updates
 */
router.get('/:bookId/status', (req, res) => {
  const { bookId } = req.params;

  // Set headers for SSE
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.setHeader('X-Accel-Buffering', 'no'); // Disable nginx buffering

  // Send initial status
  const currentStatus = getStatus(bookId);
  if (currentStatus) {
    res.write(`data: ${JSON.stringify(currentStatus)}\n\n`);
  } else {
    res.write(`data: ${JSON.stringify({
      bookId,
      status: 'unknown',
      progress: 'No status available'
    })}\n\n`);
  }

  // Register listener for updates
  const unsubscribe = registerSSEListener(bookId, (statusData) => {
    res.write(`data: ${JSON.stringify(statusData)}\n\n`);

    // Close connection when processing is complete or failed
    if (statusData.status === 'completed' || statusData.status === 'failed') {
      setTimeout(() => {
        res.end();
      }, 1000);
    }
  });

  // Handle client disconnect
  req.on('close', () => {
    unsubscribe();
    res.end();
  });
});

// GET /api/books/:bookId/segments - Get all segments with timing data
router.get('/:bookId/segments', validateBookIdParam, async (req, res) => {
  try {
    const { bookId } = req.params;
    const db = req.db;

    // #STAGE3-B: Uses Index 5 (book_id, segment_index) for efficient lookup and sorting
    const segments = await db
      .collection('segment_timings')
      .find({ book_id: bookId })
      .sort({ segment_index: 1 })
      .toArray();

    if (segments.length === 0) {
      return res.status(404).json({ error: 'No segments found for this book' });
    }

    res.json(segments);

  } catch (error) {
    console.error('Error fetching segments:', error);
    res.status(500).json({ error: error.message });
  }
});

/**
 * GET /api/books/:bookId/audio
 * Stream audio file for a book
 * 
 * SECURITY: validateBookIdParam prevents path traversal via bookId
 * (e.g., "../../../etc/passwd" would be rejected)
 */
router.get('/:bookId/audio', validateBookIdParam, async (req, res) => {
  try {
    const { bookId } = req.params;  // Validated - only a-z, 0-9, _ allowed
    const audioPath = path.join(
      __dirname,
      '../audio_reader_standalone/output',
      bookId,
      'book_continuous.wav'
    );

    // Check if file exists
    try {
      await fs.access(audioPath);
    } catch {
      return res.status(404).json({ error: 'Audio file not found' });
    }

    // Stream the audio file
    res.sendFile(audioPath);

  } catch (error) {
    console.error('Error streaming audio:', error);
    res.status(500).json({ error: error.message });
  }
});

// GET /api/books/:bookId/speaker-stats - Speaker Duration Report
router.get('/:bookId/speaker-stats', validateBookIdParam, async (req, res) => {
  try {
    const { bookId } = req.params;
    const db = req.db;

    // #STAGE3-B: Uses Index 7 (book_id, speaker) for efficient aggregation
    // This is the Speaker Duration Report - shows speaking time per character
    const speakerStats = await db
      .collection('segment_timings')
      .aggregate([
        { $match: { book_id: bookId } },  // Index 7 filters by book_id
        {
          $group: {
            _id: '$speaker',              // Index 7 groups by speaker
            duration: { $sum: '$duration' },
            segmentCount: { $sum: 1 }
          }
        },
        { $sort: { duration: -1 } }
      ])
      .toArray();

    if (speakerStats.length === 0) {
      return res.status(404).json({ error: 'No speaker data found for this book' });
    }

    // Calculate total duration and percentages
    const totalDuration = speakerStats.reduce((sum, speaker) => sum + speaker.duration, 0);

    const speakers = speakerStats.map(stat => ({
      speaker: stat._id,
      duration: parseFloat(stat.duration.toFixed(2)),
      segmentCount: stat.segmentCount,
      percentage: parseFloat(((stat.duration / totalDuration) * 100).toFixed(1))
    }));

    res.json({
      speakers,
      totalDuration: parseFloat(totalDuration.toFixed(2))
    });

  } catch (error) {
    console.error('Error fetching speaker stats:', error);
    res.status(500).json({ error: error.message });
  }
});

// GET /api/books - List all books with optional filtering
router.get('/', validateBookQueryParams, async (req, res) => {
  try {
    const db = req.db;
    const { minDuration, maxDuration, minSegments, maxSegments, startDate, endDate, title, titleRegexSafe } = req.query;

    const filter = {};

    // #STAGE3-B: Uses Index 3 (duration) for range filtering
    if (minDuration !== undefined || maxDuration !== undefined) {
      filter.duration = {};
      if (minDuration !== undefined) filter.duration.$gte = minDuration;
      if (maxDuration !== undefined) filter.duration.$lte = maxDuration;
    }

    if (minSegments !== undefined || maxSegments !== undefined) {
      filter.total_segments = {};
      if (minSegments !== undefined) filter.total_segments.$gte = minSegments;
      if (maxSegments !== undefined) filter.total_segments.$lte = maxSegments;
    }

    // #STAGE3-B: Uses Index 4 (created_at) for date range filtering
    if (startDate || endDate) {
      filter.created_at = {};
      if (startDate) filter.created_at.$gte = startDate;
      if (endDate) filter.created_at.$lte = endDate;
    }

    // #STAGE3-B: Uses Index 2 (title) for regex search
    if (title && titleRegexSafe) {
      filter.title = { $regex: titleRegexSafe, $options: 'i' };
    }

    // #STAGE3-B: Uses Index 4 (created_at DESC) for sorting
    const books = await db
      .collection('books')
      .find(filter)
      .sort({ created_at: -1 })
      .toArray();

    res.json(books);

  } catch (error) {
    console.error('Error fetching books:', error);
    res.status(500).json({ error: error.message });
  }
});

// GET /api/books/:bookId - Get metadata for a specific book
router.get('/:bookId', validateBookIdParam, async (req, res) => {
  try {
    const { bookId } = req.params;
    const db = req.db;

    // #STAGE3-B: Uses Index 1 (book_id unique) for O(log n) lookup instead of O(n) scan
    const book = await db.collection('books').findOne({ book_id: bookId });

    if (!book) {
      return res.status(404).json({ error: 'Book not found' });
    }

    res.json(book);

  } catch (error) {
    console.error('Error fetching book:', error);
    res.status(500).json({ error: error.message });
  }
});

/**
 * PATCH /api/books/:bookId
 * Update book metadata (e.g., title)
 * UPDATE REQUIREMENT
 * 
 * SECURITY: Both bookId (param) and title (body) are validated
 */
router.patch('/:bookId', validateBookIdParam, validateBookBody, async (req, res) => {
  try {
    const { bookId } = req.params;  // Validated by validateBookIdParam
    const { title } = req.body;      // Validated by validateBookBody
    const db = req.db;

    if (!title || title.trim().length === 0) {
      return res.status(400).json({ error: 'Title is required' });
    }

    // SECURITY: Safe parameterized update query
    // Both the filter {book_id: bookId} and update {$set: {title: ...}} use
    // validated values, preventing operator injection
    const result = await db.collection('books').updateOne(
      { book_id: bookId },
      {
        $set: {
          title: title.trim(),
          updated_at: new Date()
        }
      }
    );

    if (result.matchedCount === 0) {
      return res.status(404).json({ error: 'Book not found' });
    }

    // Get updated book
    const updatedBook = await db.collection('books').findOne({ book_id: bookId });

    res.json({
      message: 'Book updated successfully',
      book: updatedBook
    });

  } catch (error) {
    console.error('Error updating book:', error);
    res.status(500).json({ error: error.message });
  }
});

// #STAGE3-C: TRANSACTIONS - Delete book with multi-document transaction
router.delete('/:bookId', validateBookIdParam, async (req, res) => {
  const { bookId } = req.params;
  const db = req.db;
  const mongoClient = req.mongoClient;
  
  // 1. Start a session for the transaction
  const session = mongoClient.startSession();
  
  try {
    // 2. Execute all deletes within a transaction (ALL succeed or ALL fail)
    await session.withTransaction(async () => {
      
      // Delete from books collection
      const bookResult = await db.collection('books').deleteOne(
        { book_id: bookId },
        { session }
      );
      
      // Delete from segments collection
      await db.collection('segments').deleteMany(
        { book_id: bookId },
        { session }
      );
      
      // Delete from segment_timings collection
      await db.collection('segment_timings').deleteMany(
        { book_id: bookId },
        { session }
      );
      
      if (bookResult.deletedCount === 0) {
        console.log(`⚠️  Book '${bookId}' not found in database`);
      }
      
    }, {
      // 3. Transaction isolation level options
      readConcern: { level: 'snapshot' },  // REPEATABLE READ equivalent
      writeConcern: { w: 'majority' },
      readPreference: 'primary'
    });
    
    console.log(`✅ Transaction completed: deleted book '${bookId}' from all collections`);
    
    // Delete audio files (outside transaction - filesystem doesn't support transactions)
    const bookOutputDir = path.join(__dirname, '../audio_reader_standalone/output', bookId);
    try {
      await fs.rm(bookOutputDir, { recursive: true, force: true });
      console.log(`🗑️  Deleted files for book: ${bookId}`);
    } catch (error) {
      console.error(`Failed to delete files for ${bookId}:`, error);
    }

    res.json({ 
      message: 'Book deleted successfully', 
      bookId,
      transactionUsed: true
    });

  } catch (error) {
    // 4. Transaction automatically rolled back on error
    console.error('Error deleting book (transaction rolled back):', error);
    res.status(500).json({ 
      error: error.message,
      transactionRolledBack: true
    });
  } finally {
    // 5. Always end the session
    await session.endSession();
  }
});

module.exports = router;

