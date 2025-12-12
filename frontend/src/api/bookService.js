/**
 * API service for interacting with the backend
 */

// Backend API URL configuration
// In production: uses VITE_API_URL env var, falls back to Railway URL
// In development: uses relative path (Vite proxy handles it)
const BACKEND_URL = import.meta.env.VITE_API_URL || 
  (import.meta.env.PROD ? 'https://ansh-stg3-production.up.railway.app' : '');

const API_BASE = BACKEND_URL ? `${BACKEND_URL}/api` : '/api';
const AUDIO_BASE = BACKEND_URL ? `${BACKEND_URL}/audio` : '/audio';

/**
 * Fetch all books with optional filters
 * @param {Object} filters - Filter options
 * @param {number} filters.minDuration - Minimum duration in seconds
 * @param {number} filters.maxDuration - Maximum duration in seconds
 * @param {number} filters.minSegments - Minimum number of segments
 * @param {number} filters.maxSegments - Maximum number of segments
 * @param {string} filters.startDate - Start date (ISO string)
 * @param {string} filters.endDate - End date (ISO string)
 * @param {string} filters.title - Title search (case-insensitive)
 */
export async function fetchBooks(filters = {}) {
  const params = new URLSearchParams();
  
  if (filters.minDuration !== undefined && filters.minDuration !== null && filters.minDuration !== '') {
    params.append('minDuration', filters.minDuration);
  }
  if (filters.maxDuration !== undefined && filters.maxDuration !== null && filters.maxDuration !== '') {
    params.append('maxDuration', filters.maxDuration);
  }
  if (filters.minSegments !== undefined && filters.minSegments !== null && filters.minSegments !== '') {
    params.append('minSegments', filters.minSegments);
  }
  if (filters.maxSegments !== undefined && filters.maxSegments !== null && filters.maxSegments !== '') {
    params.append('maxSegments', filters.maxSegments);
  }
  if (filters.startDate) {
    params.append('startDate', filters.startDate);
  }
  if (filters.endDate) {
    params.append('endDate', filters.endDate);
  }
  if (filters.title) {
    params.append('title', filters.title);
  }
  
  const queryString = params.toString();
  const url = queryString ? `${API_BASE}/books?${queryString}` : `${API_BASE}/books`;
  
  try {
    const response = await fetch(url);
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `HTTP ${response.status}: Failed to fetch books`);
    }
    const text = await response.text();
    if (!text) {
      return []; // Empty response, return empty array
    }
    return JSON.parse(text);
  } catch (error) {
    console.error('fetchBooks error:', error, 'URL:', url);
    throw error;
  }
}

/**
 * Create a new book manually
 * @param {Object} bookData - Book data
 * @param {string} bookData.title - Book title (required)
 * @param {number} bookData.duration - Duration in seconds (optional)
 * @param {number} bookData.total_segments - Number of segments (optional)
 */
export async function createBook(bookData) {
  const response = await fetch(`${API_BASE}/books`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(bookData)
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to create book');
  }
  
  return response.json();
}

/**
 * Fetch a single book by ID
 */
export async function fetchBook(bookId) {
  const response = await fetch(`${API_BASE}/books/${bookId}`);
  if (!response.ok) {
    throw new Error('Failed to fetch book');
  }
  return response.json();
}

/**
 * Fetch segments for a book
 */
export async function fetchSegments(bookId) {
  const response = await fetch(`${API_BASE}/books/${bookId}/segments`);
  if (!response.ok) {
    throw new Error('Failed to fetch segments');
  }
  return response.json();
}

/**
 * Fetch speaker statistics for a book
 */
export async function getSpeakerStats(bookId) {
  const response = await fetch(`${API_BASE}/books/${bookId}/speaker-stats`);
  if (!response.ok) {
    throw new Error('Failed to fetch speaker statistics');
  }
  return response.json();
}

/**
 * Get audio URL for a book
 */
export function getAudioUrl(bookId) {
  return `${API_BASE}/books/${bookId}/audio`;
}

/**
 * Get direct audio file URL (for streaming)
 */
export function getAudioFileUrl(filename) {
  return `${AUDIO_BASE}/${filename}`;
}

/**
 * Upload a PDF file
 */
export async function uploadBook(file, title) {
  const formData = new FormData();
  formData.append('pdf', file);
  if (title) {
    formData.append('title', title);
  }
  
  const response = await fetch(`${API_BASE}/books/upload`, {
    method: 'POST',
    body: formData
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Upload failed');
  }
  
  return response.json();
}

/**
 * Update a book's metadata
 */
export async function updateBook(bookId, updates) {
  const response = await fetch(`${API_BASE}/books/${bookId}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(updates)
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to update book');
  }
  
  return response.json();
}

/**
 * Delete a book
 */
export async function deleteBook(bookId) {
  const response = await fetch(`${API_BASE}/books/${bookId}`, {
    method: 'DELETE'
  });
  
  if (!response.ok) {
    throw new Error('Failed to delete book');
  }
  
  return response.json();
}

/**
 * Subscribe to processing status updates via SSE
 */
export function subscribeToStatus(bookId, onUpdate, onError) {
  const eventSource = new EventSource(`${API_BASE}/books/${bookId}/status`);
  
  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onUpdate(data);
      
      // Close connection when complete or failed
      if (data.status === 'completed' || data.status === 'failed') {
        eventSource.close();
      }
    } catch (error) {
      console.error('Error parsing SSE data:', error);
      onError?.(error);
    }
  };
  
  eventSource.onerror = (error) => {
    console.error('SSE error:', error);
    eventSource.close();
    onError?.(error);
  };
  
  // Return cleanup function
  return () => eventSource.close();
}

