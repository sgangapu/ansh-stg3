const path = require('path');
const fs = require('fs').promises;
const { executePythonScript } = require('./pythonExecutor');

// Processing status store (in-memory for simplicity, could use Redis for production)
const processingStatus = new Map();

/**
 * Update processing status for a book
 */
function updateStatus(bookId, status, progress, error = null) {
  const statusData = {
    bookId,
    status, // 'processing', 'completed', 'failed'
    progress, // e.g., 'Step 1 of 4: Analyzing text...'
    error,
    updatedAt: new Date().toISOString()
  };

  processingStatus.set(bookId, statusData);

  // Emit to SSE clients if any are listening
  const listeners = sseListeners.get(bookId) || [];
  listeners.forEach(listener => {
    listener(statusData);
  });

  return statusData;
}

/**
 * Get processing status for a book
 */
function getStatus(bookId) {
  return processingStatus.get(bookId) || null;
}

// SSE listeners store
const sseListeners = new Map();

/**
 * Register an SSE listener for a book's processing updates
 */
function registerSSEListener(bookId, callback) {
  if (!sseListeners.has(bookId)) {
    sseListeners.set(bookId, []);
  }
  sseListeners.get(bookId).push(callback);

  // Return unsubscribe function
  return () => {
    const listeners = sseListeners.get(bookId) || [];
    const index = listeners.indexOf(callback);
    if (index > -1) {
      listeners.splice(index, 1);
    }
  };
}

/**
 * Generate sanitized book ID from title or filename
 */
function generateBookId(title) {
  return title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

/**
 * Main pipeline orchestrator
 * Executes all 4 steps of the audiobook generation process
 */
async function processAudiobook(pdfPath, title) {
  const bookId = generateBookId(title);
  const outputDir = path.join(__dirname, '../audio_reader_standalone/output');
  const bookOutputDir = path.join(outputDir, bookId);

  console.log(`\n${'='.repeat(60)}`);
  console.log(`🎵 Starting audiobook pipeline for: ${title}`);
  console.log(`📖 Book ID: ${bookId}`);
  console.log(`📁 Output: ${bookOutputDir}`);
  console.log(`${'='.repeat(60)}\n`);

  try {
    // Initialize status
    updateStatus(bookId, 'processing', 'Step 1 of 4: Analyzing text with AI...', null);

    // Step 1: Generate segments using Gemini AI
    console.log('📝 Step 1/4: Generating segments...');
    const result =     await executePythonScript('generate_segments.py', [pdfPath], {
      timeout: 300000, // 5 minutes
      onProgress: (output) => {
        // Progress is already logged by pythonExecutor
      }
    });

    // Find the actual output directory created by generate_segments.py
    // It uses the PDF filename, which may include timestamp
    const fs = require('fs').promises;
    const outputDirs = await fs.readdir(outputDir);

    // Find directory that contains our segments.json
    let actualOutputDir = null;
    for (const dir of outputDirs) {
      const dirPath = path.join(outputDir, dir);
      const segmentsPath = path.join(dirPath, 'segments.json');
      try {
        await fs.access(segmentsPath);
        // Check if this is the most recent one (in case multiple exist)
        const stats = await fs.stat(segmentsPath);
        if (!actualOutputDir || stats.mtimeMs > (await fs.stat(path.join(actualOutputDir, 'segments.json'))).mtimeMs) {
          actualOutputDir = dirPath;
        }
      } catch { }
    }

    if (!actualOutputDir) {
      throw new Error('segments.json not found after generation');
    }

    console.log(`📁 Found output directory: ${actualOutputDir}`);

    updateStatus(bookId, 'processing', 'Step 2 of 4: Storing segments in database...', null);

    // Step 2: Import segments to MongoDB
    console.log('💾 Step 2/4: Importing segments to MongoDB...');
    const segmentsJsonPath = path.join(actualOutputDir, 'segments.json');
    await executePythonScript('mongo_service.py', ['import', segmentsJsonPath, '--title', title], {
      timeout: 60000 // 1 minute
    });

    updateStatus(bookId, 'processing', 'Step 3 of 4: Generating audio (this may take several minutes)...', null);

    // Step 3: Generate audio with Cartesia TTS
    // Use --segments-json which will use the segments.json file and its directory
    // This avoids the book_id subdirectory issue
    console.log('🎙️  Step 3/4: Generating audio...');
    console.log(`   Reading segments from: ${segmentsJsonPath}`);
    console.log(`   Output will be saved to: ${actualOutputDir}`);

    const scriptName = 'audio_reader.py';

    await executePythonScript(scriptName, ['--segments-json', segmentsJsonPath], {
      timeout: 1800000, // 30 minutes for long books
      onProgress: (output) => {
        // Forward progress updates
        // Note: pythonExecutor already logs to console, so we don't need to log here
      }
    });

    updateStatus(bookId, 'processing', 'Step 4 of 4: Creating timing data...', null);

    // Step 4: Import timing data
    console.log('⏱️  Step 4/4: Importing timing data...');
    const timingJsonPath = path.join(actualOutputDir, 'segment_timings.json');
    await executePythonScript('timing_service.py', ['import', timingJsonPath, bookId], {
      timeout: 60000 // 1 minute
    });

    // Rename output directory to match bookId for consistent frontend access
    if (path.basename(actualOutputDir) !== bookId) {
      const fs = require('fs').promises;
      const targetDir = path.join(outputDir, bookId);

      // Remove target if it exists (edge case)
      try {
        await fs.rm(targetDir, { recursive: true, force: true });
      } catch { }

      // Rename to bookId
      await fs.rename(actualOutputDir, targetDir);
      console.log(`📁 Renamed output directory to: ${bookId}`);
    }

    // Success!
    console.log(`\n${'='.repeat(60)}`);
    console.log(`✅ Pipeline completed successfully for: ${title}`);
    console.log(`${'='.repeat(60)}\n`);

    updateStatus(bookId, 'completed', 'Complete! Audiobook ready to play.', null);

    return { bookId, status: 'completed' };

  } catch (error) {
    console.error(`\n${'='.repeat(60)}`);
    console.error(`❌ Pipeline failed for: ${title}`);
    console.error(`Error: ${error.message}`);
    console.error(`${'='.repeat(60)}\n`);

    updateStatus(bookId, 'failed', 'Failed', error.message);

    throw error;
  }
}

/**
 * Check if a book is currently being processed
 */
function isProcessing(bookId) {
  const status = getStatus(bookId);
  return status && status.status === 'processing';
}

module.exports = {
  processAudiobook,
  updateStatus,
  getStatus,
  registerSSEListener,
  isProcessing,
  generateBookId
};

