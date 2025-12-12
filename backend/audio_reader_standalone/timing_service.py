#!/usr/bin/env python3
"""
Timing Service - Manage segment timing data in MongoDB

This service handles:
1. Importing segment timing data from segment_timings.json files
2. Querying timing data to find audio playback positions
3. Managing a separate timing collection for efficient lookups
"""

import os
import sys
import json
import logging
from typing import Dict, List, Optional
from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING, DESCENDING

# Load environment variables
load_dotenv()

# Configure logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger(__name__)


class TimingService:
    """Service for managing audiobook segment timing data in MongoDB"""
    
    def __init__(self, mongo_uri: str = None, db_name: str = None):
        """
        Initialize the timing service.
        
        Args:
            mongo_uri: MongoDB connection URI (default: from env or localhost)
            db_name: Database name (default: from env or audiobooks_db)
        """
        self.mongo_uri = mongo_uri or os.getenv("MONGO_URI", "mongodb://localhost:27017/")
        self.db_name = db_name or os.getenv("MONGO_DB_NAME", "audiobooks_db")
        
        # Connect to MongoDB
        self.client = MongoClient(self.mongo_uri)
        self.db = self.client[self.db_name]
        self.timings_collection = self.db.segment_timings
        self.books_collection = self.db.books
        
        # Create indexes for efficient querying
        self._create_indexes()
        
        logger.info(f"✅ Connected to MongoDB: {self.db_name}")
        logger.info(f"📊 Using collection: segment_timings")
    
    # #STAGE3-B: DATABASE INDEXES
    def _create_indexes(self):
        """Create indexes, handling cases where equivalent indexes already exist with different names."""
        from pymongo.errors import OperationFailure
        
        def safe_create_index(collection, keys, **kwargs):
            """Create index, ignoring if equivalent index exists with different name."""
            try:
                collection.create_index(keys, **kwargs)
            except OperationFailure as e:
                # Code 85 = IndexOptionsConflict (index exists with different name)
                if e.code == 85:
                    logger.debug(f"Index already exists on {keys} (different name), skipping")
                else:
                    raise
        
        # #STAGE3-B Index 5: (book_id, segment_index) - for segment lookup
        safe_create_index(
            self.timings_collection,
            [("book_id", ASCENDING), ("segment_index", ASCENDING)],
            unique=True,
            name="idx_timings_book_segment"
        )
        
        safe_create_index(
            self.timings_collection,
            [("book_id", ASCENDING)],
            name="idx_timings_book_id"
        )
        
        # #STAGE3-B Index 6: (book_id, start_time) - for find_segment_at_time()
        safe_create_index(
            self.timings_collection,
            [("book_id", ASCENDING), ("start_time", ASCENDING)],
            name="idx_timings_book_start_time"
        )
        
        # #STAGE3-B Index 7: (book_id, speaker) - for speaker-stats report
        safe_create_index(
            self.timings_collection,
            [("book_id", ASCENDING), ("speaker", ASCENDING)],
            name="idx_timings_book_speaker"
        )
        
        logger.debug("📇 Indexes created/verified for segment_timings collection")
    
    def import_timings(self, timing_json_path: str, book_id: str) -> int:
        """
        Import segment timing data from a segment_timings.json file.
        
        Args:
            timing_json_path: Path to segment_timings.json file
            book_id: Book ID to associate with these timings
            
        Returns:
            Number of segments imported
        """
        try:
            # Load timing data
            with open(timing_json_path, 'r', encoding='utf-8') as f:
                timing_data = json.load(f)
            
            segments = timing_data.get('segments', [])
            total_duration = timing_data.get('total_duration', 0)
            
            logger.info(f"📥 Importing {len(segments)} timing entries for book: {book_id}")
            logger.info(f"📊 Total duration: {total_duration:.2f}s ({total_duration/60:.2f} minutes)")
            
            # Delete existing timings for this book
            deleted = self.timings_collection.delete_many({"book_id": book_id})
            if deleted.deleted_count > 0:
                logger.info(f"🗑️  Removed {deleted.deleted_count} old timing entries")
            
            # Prepare documents for insertion
            timing_docs = []
            for segment in segments:
                doc = {
                    "book_id": book_id,
                    "segment_index": segment["segment_index"],
                    "speaker": segment.get("speaker", "unknown"),
                    "text": segment.get("text", ""),
                    "start_time": segment["start_time"],
                    "duration": segment["duration"],
                    "end_time": segment["end_time"]
                }
                timing_docs.append(doc)
            
            # Bulk insert
            if timing_docs:
                result = self.timings_collection.insert_many(timing_docs)
                logger.info(f"✅ Imported {len(result.inserted_ids)} timing entries")
            
            # Update the book document with the total duration
            if total_duration > 0:
                update_result = self.books_collection.update_one(
                    {"book_id": book_id},
                    {"$set": {"duration": total_duration}}
                )
                if update_result.matched_count > 0:
                    logger.info(f"✅ Updated book duration: {total_duration:.2f}s")
                else:
                    logger.warning(f"⚠️  Book '{book_id}' not found in books collection to update duration")
            
            return len(timing_docs)
            
        except FileNotFoundError:
            logger.error(f"❌ Timing file not found: {timing_json_path}")
            raise
        except Exception as e:
            logger.error(f"❌ Error importing timings: {e}")
            raise
    
    def get_segment_timing(self, book_id: str, segment_index: int) -> Optional[Dict]:
        """
        Get timing information for a specific segment.
        
        Args:
            book_id: Book ID
            segment_index: Segment index (0-based)
            
        Returns:
            Dictionary with timing info or None if not found
        """
        timing = self.timings_collection.find_one(
            {"book_id": book_id, "segment_index": segment_index},
            {"_id": 0}  # Exclude MongoDB _id field
        )
        return timing
    
    def get_all_timings(self, book_id: str) -> List[Dict]:
        """
        Get all timing information for a book.
        
        Args:
            book_id: Book ID
            
        Returns:
            List of timing dictionaries, sorted by segment_index
        """
        timings = list(self.timings_collection.find(
            {"book_id": book_id},
            {"_id": 0}
        ).sort("segment_index", ASCENDING))
        
        return timings
    
    def find_segment_at_time(self, book_id: str, timestamp: float) -> Optional[Dict]:
        """Find which segment is playing at a given timestamp (for audio sync)."""
        # #STAGE3-B: Uses Index 6 (book_id, start_time) for efficient time-based lookup
        # This query finds what text to highlight when audio is at position X
        timing = self.timings_collection.find_one(
            {
                "book_id": book_id,
                "start_time": {"$lte": timestamp},
                "end_time": {"$gt": timestamp}
            },
            {"_id": 0}
        )
        return timing
    
    def get_book_duration(self, book_id: str) -> float:
        """
        Get total duration of a book in seconds.
        
        Args:
            book_id: Book ID
            
        Returns:
            Total duration in seconds, or 0 if not found
        """
        # Find the segment with the highest end_time
        last_segment = self.timings_collection.find_one(
            {"book_id": book_id},
            {"_id": 0, "end_time": 1},
            sort=[("end_time", DESCENDING)]
        )
        
        if last_segment:
            return last_segment["end_time"]
        return 0.0
    
    def search_by_text(self, book_id: str, search_text: str) -> List[Dict]:
        """
        Search for segments containing specific text.
        
        Args:
            book_id: Book ID
            search_text: Text to search for (case-insensitive)
            
        Returns:
            List of matching timing dictionaries
        """
        # Use regex for case-insensitive search
        timings = list(self.timings_collection.find(
            {
                "book_id": book_id,
                "text": {"$regex": search_text, "$options": "i"}
            },
            {"_id": 0}
        ).sort("segment_index", ASCENDING))
        
        return timings
    
    def close(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            logger.info("🔌 MongoDB connection closed")


def main():
    """Command-line interface for timing service"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Manage audiobook segment timing data in MongoDB"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Import command
    import_parser = subparsers.add_parser("import", help="Import timing data from JSON file")
    import_parser.add_argument("timing_file", help="Path to segment_timings.json file")
    import_parser.add_argument("book_id", help="Book ID to associate with timings")
    
    # Get command
    get_parser = subparsers.add_parser("get", help="Get timing for a specific segment")
    get_parser.add_argument("book_id", help="Book ID")
    get_parser.add_argument("segment_index", type=int, help="Segment index")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List all timings for a book")
    list_parser.add_argument("book_id", help="Book ID")
    
    # Find command
    find_parser = subparsers.add_parser("find", help="Find segment at a specific timestamp")
    find_parser.add_argument("book_id", help="Book ID")
    find_parser.add_argument("timestamp", type=float, help="Timestamp in seconds")
    
    # Duration command
    duration_parser = subparsers.add_parser("duration", help="Get total duration of a book")
    duration_parser.add_argument("book_id", help="Book ID")
    
    # Search command
    search_parser = subparsers.add_parser("search", help="Search segments by text")
    search_parser.add_argument("book_id", help="Book ID")
    search_parser.add_argument("text", help="Text to search for")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Initialize service
    service = TimingService()
    
    try:
        if args.command == "import":
            count = service.import_timings(args.timing_file, args.book_id)
            print(f"\n✅ Successfully imported {count} timing entries for '{args.book_id}'")
            
        elif args.command == "get":
            timing = service.get_segment_timing(args.book_id, args.segment_index)
            if timing:
                print(f"\n📊 Segment {args.segment_index} timing:")
                print(json.dumps(timing, indent=2))
            else:
                print(f"\n❌ No timing found for segment {args.segment_index}")
                
        elif args.command == "list":
            timings = service.get_all_timings(args.book_id)
            print(f"\n📊 {len(timings)} timing entries for '{args.book_id}':")
            for t in timings[:10]:  # Show first 10
                print(f"  [{t['segment_index']}] {t['start_time']:.2f}s - {t['end_time']:.2f}s: {t['text'][:50]}...")
            if len(timings) > 10:
                print(f"  ... and {len(timings) - 10} more")
                
        elif args.command == "find":
            timing = service.find_segment_at_time(args.book_id, args.timestamp)
            if timing:
                print(f"\n📊 At {args.timestamp:.2f}s:")
                print(json.dumps(timing, indent=2))
            else:
                print(f"\n❌ No segment found at timestamp {args.timestamp:.2f}s")
                
        elif args.command == "duration":
            duration = service.get_book_duration(args.book_id)
            print(f"\n📊 Total duration of '{args.book_id}':")
            print(f"  {duration:.2f} seconds ({duration/60:.2f} minutes)")
            
        elif args.command == "search":
            timings = service.search_by_text(args.book_id, args.text)
            print(f"\n🔍 Found {len(timings)} segments containing '{args.text}':")
            for t in timings:
                print(f"  [{t['segment_index']}] {t['start_time']:.2f}s: {t['text']}")
                
    finally:
        service.close()


if __name__ == "__main__":
    main()

