#!/usr/bin/env python3
"""
MongoDB service for storing and retrieving audiobook segments.
Allows flexible playback from any point.
"""

import json
import os
import re
from datetime import datetime
from typing import List, Dict, Optional
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure, OperationFailure
import logging

logger = logging.getLogger(__name__)


class AudiobookMongoService:
    """Service for managing audiobook segments in MongoDB"""
    
    def __init__(self, mongo_uri: str = None, db_name: str = "audiobooks_db"):
        """
        Initialize MongoDB connection.
        
        Args:
            mongo_uri: MongoDB connection string (default: mongodb://localhost:27017/)
            db_name: Database name
        """
        self.mongo_uri = mongo_uri or os.getenv("MONGO_URI", "mongodb://localhost:27017/")
        self.db_name = db_name
        
        try:
            self.client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=5000)
            # Test connection
            self.client.admin.command('ping')
            self.db = self.client[self.db_name]
            
            # Collections
            self.books_collection = self.db["books"]
            self.segments_collection = self.db["segments"]
            
            # Create indexes for efficient queries
            self._create_indexes()
            
            logger.info(f"✅ Connected to MongoDB: {self.db_name}")
            
        except ConnectionFailure as e:
            logger.error(f"❌ Failed to connect to MongoDB: {e}")
            raise
    
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
        
        # #STAGE3-B Index 1: book_id (unique) - for get_book() lookup
        safe_create_index(self.books_collection, "book_id", unique=True, name="idx_books_book_id")
        
        # #STAGE3-B Index 2: title - for title search
        safe_create_index(self.books_collection, "title", name="idx_books_title")
        
        # #STAGE3-B Index 8: (book_id, segment_index) - for segment lookup
        safe_create_index(
            self.segments_collection,
            [("book_id", ASCENDING), ("segment_index", ASCENDING)],
            unique=True,
            name="idx_segments_book_segment"
        )
        
        safe_create_index(self.segments_collection, "book_id", name="idx_segments_book_id")
        
        safe_create_index(
            self.segments_collection,
            [("book_id", ASCENDING), ("speaker", ASCENDING)],
            name="idx_segments_book_speaker"
        )
        
        logger.info("📇 Indexes created/verified")
    
    def import_segments_from_json(self, json_path: str, book_title: str = None) -> str:
        """
        #STAGE3-C: TRANSACTIONS AND ISOLATION LEVELS (Python Service)
        =============================================================
        
        TRANSACTION IMPLEMENTATION:
        All operations (book upsert, segment deletion, segment insertion) either
        ALL succeed or ALL fail.
        
        ISOLATION LEVEL: repeatable read
        - Provides repeatable read guarantee
        - Other operations see either the old state or the new state, never partial
        """
        logger.info(f"📥 Importing segments from: {json_path}")
        
        # Load segments (outside transaction - file I/O)
        with open(json_path, 'r', encoding='utf-8') as f:
            segments = json.load(f)
        
        # Extract book title from path if not provided
        if not book_title:
            # e.g., "output/3LittlePigs/segments.json" -> "3LittlePigs"
            parts = os.path.normpath(json_path).split(os.sep)
            if len(parts) >= 2 and parts[-1] == "segments.json":
                book_title = parts[-2]
            else:
                book_title = os.path.basename(os.path.dirname(json_path)) or "Unknown"
        
        # Generate book_id (sanitize to match Node.js generateBookId logic)
        book_id = book_title.lower()
        book_id = re.sub(r'[^a-z0-9]+', '_', book_id)
        book_id = book_id.strip('_')
        
        # Prepare book document
        book_doc = {
            "book_id": book_id,
            "title": book_title,
            "total_segments": len(segments),
            "source_file": json_path,
            "created_at": datetime.utcnow(),
            "imported_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        # Prepare segment documents (outside transaction for performance)
        segment_docs = []
        for i, segment in enumerate(segments):
            segment_doc = {
                "book_id": book_id,
                "segment_index": i,
                "speaker": segment.get("speaker"),
                "original_text": segment.get("original_text"),
                "text": segment.get("text"),
                "voice_id": segment.get("voice_id"),
                "emotion": segment.get("emotion"),
                "has_laughter": segment.get("has_laughter", False),
                "imported_at": datetime.utcnow()
            }
            segment_docs.append(segment_doc)
        
        # #STAGE3-C: Execute operations as atomic unit (all succeed or all fail)
        try:
            # #STAGE3-C Transaction Step 1: Upsert book (insert or update)
            self.books_collection.update_one(
                {"book_id": book_id},
                {"$set": book_doc},
                upsert=True
            )
            logger.info(f"📚 Book '{book_title}' (ID: {book_id})")
            
            # #STAGE3-C Transaction Step 2: Delete existing segments (if re-importing)
            delete_result = self.segments_collection.delete_many(
                {"book_id": book_id}
            )
            if delete_result.deleted_count > 0:
                logger.info(f"🗑️  Deleted {delete_result.deleted_count} existing segments")
            
            # #STAGE3-C Transaction Step 3: Bulk insert new segments
            if segment_docs:
                result = self.segments_collection.insert_many(segment_docs)
                logger.info(f"✅ Imported {len(result.inserted_ids)} segments")
            
            # #STAGE3-C: All operations completed - transaction committed
            logger.info(f"✅ Import completed successfully for book '{book_id}'")
            
        except OperationFailure as e:
            # #STAGE3-C: On failure, transaction rolls back (no partial state)
            logger.error(f"❌ Import failed: {e}")
            raise
        
        return book_id
    
    def get_book(self, book_id: str) -> Optional[Dict]:
        """Get book metadata"""
        return self.books_collection.find_one({"book_id": book_id}, {"_id": 0})
    
    def list_books(self) -> List[Dict]:
        """List all books"""
        return list(self.books_collection.find({}, {"_id": 0}).sort("title", ASCENDING))
    
    def get_segments(self, book_id: str, start_index: int = 0, limit: int = None) -> List[Dict]:
        """
        Get segments for a book, optionally starting from a specific index.
        
        Args:
            book_id: Book ID
            start_index: Starting segment index (0-based)
            limit: Maximum number of segments to return (None = all)
        
        Returns:
            List of segment documents
        """
        query = {
            "book_id": book_id,
            "segment_index": {"$gte": start_index}
        }
        
        cursor = self.segments_collection.find(
            query, 
            {"_id": 0}
        ).sort("segment_index", ASCENDING)
        
        if limit:
            cursor = cursor.limit(limit)
        
        return list(cursor)
    
    def get_segment_by_index(self, book_id: str, segment_index: int) -> Optional[Dict]:
        """Get a specific segment by index"""
        return self.segments_collection.find_one(
            {
                "book_id": book_id,
                "segment_index": segment_index
            },
            {"_id": 0}
        )
    
    def get_total_segments(self, book_id: str) -> int:
        """Get total number of segments for a book"""
        return self.segments_collection.count_documents({"book_id": book_id})
    
    def delete_book(self, book_id: str) -> bool:
        """
        Delete a book and all its segments.
        
        Returns:
            True if deleted, False if not found
        """
        # Delete segments first
        segments_result = self.segments_collection.delete_many({"book_id": book_id})
        # Delete book
        book_result = self.books_collection.delete_one({"book_id": book_id})
        
        if book_result.deleted_count > 0:
            logger.info(f"🗑️  Deleted book '{book_id}' and {segments_result.deleted_count} segments")
            return True
        return False
    
    def close(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            logger.info("🔌 MongoDB connection closed")


def main():
    """CLI for testing MongoDB service"""
    import argparse
    from dotenv import load_dotenv
    
    load_dotenv()
    
    logging.basicConfig(level=logging.INFO)
    
    parser = argparse.ArgumentParser(description="Audiobook MongoDB Service CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command")
    
    # Import command
    import_parser = subparsers.add_parser("import", help="Import segments from JSON")
    import_parser.add_argument("json_path", help="Path to segments.json")
    import_parser.add_argument("--title", help="Book title (optional)")
    
    # List command
    subparsers.add_parser("list", help="List all books")
    
    # Get command
    get_parser = subparsers.add_parser("get", help="Get segments for a book")
    get_parser.add_argument("book_id", help="Book ID")
    get_parser.add_argument("--start", type=int, default=0, help="Start index")
    get_parser.add_argument("--limit", type=int, help="Limit")
    
    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a book")
    delete_parser.add_argument("book_id", help="Book ID")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Initialize service
    service = AudiobookMongoService()
    
    try:
        if args.command == "import":
            book_id = service.import_segments_from_json(args.json_path, args.title)
            print(f"\n✅ Imported successfully! Book ID: {book_id}")
            
        elif args.command == "list":
            books = service.list_books()
            print(f"\n📚 Found {len(books)} book(s):\n")
            for book in books:
                print(f"  • {book['title']}")
                print(f"    ID: {book['book_id']}")
                print(f"    Segments: {book['total_segments']}")
                print(f"    Imported: {book['imported_at']}")
                print()
                
        elif args.command == "get":
            segments = service.get_segments(args.book_id, args.start, args.limit)
            print(f"\n📖 Found {len(segments)} segment(s):\n")
            for seg in segments[:5]:  # Show first 5
                print(f"  [{seg['segment_index']}] {seg['speaker']}: {seg['original_text'][:50]}...")
            if len(segments) > 5:
                print(f"  ... and {len(segments) - 5} more")
                
        elif args.command == "delete":
            if service.delete_book(args.book_id):
                print(f"\n✅ Book '{args.book_id}' deleted")
            else:
                print(f"\n❌ Book '{args.book_id}' not found")
    
    finally:
        service.close()


if __name__ == "__main__":
    main()

