#!/usr/bin/env python3
"""
Example usage of the Timing Service

This demonstrates how to:
1. Import timing data into MongoDB
2. Query timing information for playback control
3. Search and navigate segments
"""

from timing_service import TimingService
import json

def example_import_timings():
    """Example: Import timing data from segment_timings.json"""
    print("=" * 60)
    print("EXAMPLE 1: Import Timing Data")
    print("=" * 60)
    
    service = TimingService()
    
    # Import timing data for Three Little Pigs
    timing_file = "output/three_little_pigs/segment_timings.json"
    book_id = "three_little_pigs"
    
    count = service.import_timings(timing_file, book_id)
    print(f"\n✅ Imported {count} timing entries")
    
    service.close()


def example_query_segment():
    """Example: Get timing for a specific segment"""
    print("\n" + "=" * 60)
    print("EXAMPLE 2: Query Specific Segment")
    print("=" * 60)
    
    service = TimingService()
    
    # User wants to start at segment 15
    book_id = "three_little_pigs"
    segment_index = 15
    
    timing = service.get_segment_timing(book_id, segment_index)
    
    if timing:
        print(f"\n📊 Segment {segment_index} info:")
        print(f"   Speaker: {timing['speaker']}")
        print(f"   Text: {timing['text']}")
        print(f"   Start time: {timing['start_time']:.2f}s")
        print(f"   Duration: {timing['duration']:.2f}s")
        print(f"\n💡 To play from this segment:")
        print(f"   audio_player.seek({timing['start_time']:.2f})")
    
    service.close()


def example_find_segment_at_time():
    """Example: Find which segment is playing at a given time"""
    print("\n" + "=" * 60)
    print("EXAMPLE 3: Find Segment at Timestamp")
    print("=" * 60)
    
    service = TimingService()
    
    # User is at 45.5 seconds in the audiobook
    book_id = "three_little_pigs"
    timestamp = 45.5
    
    timing = service.find_segment_at_time(book_id, timestamp)
    
    if timing:
        print(f"\n📊 At {timestamp:.2f}s, playing:")
        print(f"   Segment: {timing['segment_index']}")
        print(f"   Speaker: {timing['speaker']}")
        print(f"   Text: {timing['text']}")
        print(f"   Progress: {timestamp - timing['start_time']:.2f}s / {timing['duration']:.2f}s")
    
    service.close()


def example_search_text():
    """Example: Search for segments containing specific text"""
    print("\n" + "=" * 60)
    print("EXAMPLE 4: Search by Text")
    print("=" * 60)
    
    service = TimingService()
    
    # User wants to find all segments where the wolf appears
    book_id = "three_little_pigs"
    search_term = "wolf"
    
    results = service.search_by_text(book_id, search_term)
    
    print(f"\n🔍 Found {len(results)} segments containing '{search_term}':")
    for r in results[:5]:  # Show first 5
        print(f"\n   Segment {r['segment_index']} at {r['start_time']:.2f}s:")
        print(f"   {r['text'][:80]}...")
    
    service.close()


def example_get_duration():
    """Example: Get total audiobook duration"""
    print("\n" + "=" * 60)
    print("EXAMPLE 5: Get Total Duration")
    print("=" * 60)
    
    service = TimingService()
    
    book_id = "three_little_pigs"
    duration = service.get_book_duration(book_id)
    
    print(f"\n📊 '{book_id}' duration:")
    print(f"   {duration:.2f} seconds")
    print(f"   {duration/60:.2f} minutes")
    print(f"   {int(duration//60)}:{int(duration%60):02d} (mm:ss)")
    
    service.close()


def example_playback_control():
    """Example: Simulating a media player with segment-based navigation"""
    print("\n" + "=" * 60)
    print("EXAMPLE 6: Media Player Simulation")
    print("=" * 60)
    
    service = TimingService()
    book_id = "three_little_pigs"
    
    # Simulate user actions
    print("\n📱 User Interface Actions:\n")
    
    # Action 1: Skip to segment 10
    print("1️⃣ User clicks 'Skip to segment 10'")
    timing = service.get_segment_timing(book_id, 10)
    if timing:
        print(f"   → Seek to {timing['start_time']:.2f}s")
        print(f"   → Now playing: {timing['text'][:60]}...")
    
    # Action 2: User scrubs to 30 seconds
    print("\n2️⃣ User scrubs timeline to 30s")
    timing = service.find_segment_at_time(book_id, 30.0)
    if timing:
        print(f"   → Currently on segment {timing['segment_index']}")
        print(f"   → Speaker: {timing['speaker']}")
        print(f"   → Playing: {timing['text'][:60]}...")
    
    # Action 3: Previous segment
    print("\n3️⃣ User clicks 'Previous Segment'")
    current_segment = timing['segment_index']
    prev_timing = service.get_segment_timing(book_id, current_segment - 1)
    if prev_timing:
        print(f"   → Seek to {prev_timing['start_time']:.2f}s")
        print(f"   → Now playing segment {prev_timing['segment_index']}")
    
    # Action 4: Next segment
    print("\n4️⃣ User clicks 'Next Segment'")
    next_timing = service.get_segment_timing(book_id, current_segment + 1)
    if next_timing:
        print(f"   → Seek to {next_timing['start_time']:.2f}s")
        print(f"   → Now playing segment {next_timing['segment_index']}")
    
    service.close()


if __name__ == "__main__":
    print("\n🎵 AUDIOBOOK TIMING SERVICE EXAMPLES\n")
    
    # Run all examples
    try:
        example_import_timings()
        example_query_segment()
        example_find_segment_at_time()
        example_search_text()
        example_get_duration()
        example_playback_control()
        
        print("\n" + "=" * 60)
        print("✅ All examples completed successfully!")
        print("=" * 60)
        print("\n💡 Try the CLI:")
        print("   python timing_service.py --help")
        print("   python timing_service.py import output/three_little_pigs/segment_timings.json three_little_pigs")
        print("   python timing_service.py get three_little_pigs 15")
        print("   python timing_service.py find three_little_pigs 45.5")
        print("   python timing_service.py search three_little_pigs wolf")
        print()
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\n💡 Make sure MongoDB is running and timings are imported:")
        print("   python timing_service.py import output/three_little_pigs/segment_timings.json three_little_pigs")

