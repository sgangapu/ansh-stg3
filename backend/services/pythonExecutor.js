const { spawn } = require('child_process');
const path = require('path');

// Path to Python virtual environment
const PYTHON_BIN = path.join(__dirname, '../audio_reader_standalone/venv/bin/python');
const SCRIPTS_DIR = path.join(__dirname, '../audio_reader_standalone');

/**
 * Execute a Python script with arguments
 * @param {string} scriptName - Name of the Python script (e.g., 'generate_segments.py')
 * @param {string[]} args - Arguments to pass to the script
 * @param {Object} options - Additional options
 * @returns {Promise<{stdout: string, stderr: string, exitCode: number}>}
 */
function executePythonScript(scriptName, args = [], options = {}) {
  return new Promise((resolve, reject) => {
    const scriptPath = path.join(SCRIPTS_DIR, scriptName);
    const { onProgress, timeout = 600000 } = options; // 10 min default timeout

    console.log(`🐍 Executing: ${PYTHON_BIN} ${scriptPath} ${args.join(' ')}`);

    const pythonProcess = spawn(PYTHON_BIN, [scriptPath, ...args], {
      cwd: SCRIPTS_DIR,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: '1' // Ensure real-time output
      }
    });

    let stdout = '';
    let stderr = '';
    let timedOut = false;

    // Set timeout
    const timeoutId = setTimeout(() => {
      timedOut = true;
      pythonProcess.kill('SIGTERM');
      reject(new Error(`Script ${scriptName} timed out after ${timeout}ms`));
    }, timeout);

    // Capture stdout
    pythonProcess.stdout.on('data', (data) => {
      const output = data.toString();
      stdout += output;
      console.log(`[${scriptName}] ${output.trim()}`);

      // Call progress callback if provided
      if (onProgress) {
        onProgress(output.trim());
      }
    });

    // Capture stderr
    pythonProcess.stderr.on('data', (data) => {
      const output = data.toString();
      stderr += output;
      
      // Check if this is actually an error or just logging
      const isError = output.includes('ERROR') || output.includes('Traceback') || output.includes('Exception') || output.includes('Fatal');
      
      if (isError) {
        console.error(`[${scriptName}] ERROR: ${output.trim()}`);
      } else {
        // Treat as info log
        console.log(`[${scriptName}] ${output.trim()}`);
      }

      // Some Python scripts log to stderr even for info messages
      if (onProgress) {
        onProgress(output.trim());
      }
    });

    // Handle process completion
    pythonProcess.on('close', (exitCode) => {
      clearTimeout(timeoutId);

      if (timedOut) {
        return; // Already rejected with timeout error
      }

      if (exitCode === 0) {
        console.log(`✅ ${scriptName} completed successfully`);
        resolve({ stdout, stderr, exitCode });
      } else {
        console.error(`❌ ${scriptName} failed with exit code ${exitCode}`);
        reject(new Error(`${scriptName} failed with exit code ${exitCode}\n${stderr || stdout}`));
      }
    });

    // Handle process errors
    pythonProcess.on('error', (error) => {
      clearTimeout(timeoutId);
      console.error(`❌ Failed to execute ${scriptName}:`, error);
      reject(new Error(`Failed to start Python process: ${error.message}`));
    });
  });
}

/**
 * Validate that Python environment is available
 */
async function validatePythonEnvironment() {
  try {
    await executePythonScript('--version', [], { timeout: 5000 });
    return true;
  } catch (error) {
    console.error('❌ Python environment validation failed:', error);
    return false;
  }
}

module.exports = {
  executePythonScript,
  validatePythonEnvironment,
  PYTHON_BIN,
  SCRIPTS_DIR
};

