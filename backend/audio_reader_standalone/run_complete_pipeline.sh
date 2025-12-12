#!/bin/bash
# Complete Audiobook Pipeline
# Runs the entire process: PDF → Segments → MongoDB → Audio → Timing

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}        🎵 COMPLETE AUDIOBOOK GENERATION PIPELINE 🎵${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# Get PDF path from argument or use default
PDF_PATH="${1:-The Tortoise and the Hare.pdf}"
BOOK_NAME=$(basename "$PDF_PATH" .pdf)
BOOK_ID=$(echo "$BOOK_NAME" | tr '[:upper:]' '[:lower:]' | tr ' ' '_')

echo -e "${GREEN}📖 PDF:${NC} $PDF_PATH"
echo -e "${GREEN}📚 Book Name:${NC} $BOOK_NAME"
echo -e "${GREEN}🆔 Book ID:${NC} $BOOK_ID"
echo ""

# Check if PDF exists
if [ ! -f "$PDF_PATH" ]; then
    echo -e "${RED}❌ Error: PDF file not found: $PDF_PATH${NC}"
    exit 1
fi

# Activate virtual environment
echo -e "${YELLOW}🔧 Activating virtual environment...${NC}"
source venv/bin/activate

# Step 1: Generate segments from PDF using Gemini
echo -e "\n${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}STEP 1: Generate Segments with Gemini AI${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
python generate_segments.py "$PDF_PATH"

SEGMENTS_JSON="output/$BOOK_NAME/segments.json"
if [ ! -f "$SEGMENTS_JSON" ]; then
    echo -e "${RED}❌ Error: Segments JSON not created${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Segments created: $SEGMENTS_JSON${NC}"

# Step 2: Import segments to MongoDB
echo -e "\n${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}STEP 2: Import Segments to MongoDB${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
python mongo_service.py import "$SEGMENTS_JSON" --title "$BOOK_NAME"
echo -e "${GREEN}✅ Segments imported to MongoDB (book_id: $BOOK_ID)${NC}"

# Step 3: Generate audio with timing data
echo -e "\n${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}STEP 3: Generate Audio with Cartesia (with timing data)${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
python audio_reader.py --book-id "$BOOK_ID"

AUDIO_FILE="output/$BOOK_ID/book_continuous.wav"
TIMING_JSON="output/$BOOK_ID/segment_timings.json"

if [ ! -f "$AUDIO_FILE" ]; then
    echo -e "${RED}❌ Error: Audio file not created${NC}"
    exit 1
fi
if [ ! -f "$TIMING_JSON" ]; then
    echo -e "${RED}❌ Error: Timing JSON not created${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Audio generated: $AUDIO_FILE${NC}"
echo -e "${GREEN}✅ Timing data created: $TIMING_JSON${NC}"

# Step 4: Import timing data to MongoDB
echo -e "\n${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}STEP 4: Import Timing Data to MongoDB${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
python timing_service.py import "$TIMING_JSON" "$BOOK_ID"
echo -e "${GREEN}✅ Timing data imported to MongoDB${NC}"

# Summary
echo -e "\n${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}        ✅ PIPELINE COMPLETED SUCCESSFULLY! ✅${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}📊 Generated Files:${NC}"
echo -e "   📄 Segments: $SEGMENTS_JSON"
echo -e "   🎵 Audio: $AUDIO_FILE"
echo -e "   ⏱️  Timing: $TIMING_JSON"
echo ""
echo -e "${YELLOW}📊 MongoDB Data:${NC}"
echo -e "   📚 Book ID: $BOOK_ID"
echo -e "   📝 Segments Collection: segments"
echo -e "   ⏱️  Timing Collection: segment_timings"
echo ""
echo -e "${YELLOW}🎯 Next Steps:${NC}"
echo -e "   • Play audio: open $AUDIO_FILE"
echo -e "   • List books: python mongo_service.py list"
echo -e "   • Query timing: python timing_service.py get $BOOK_ID 0"
echo -e "   • Search text: python timing_service.py search $BOOK_ID <search_term>"
echo ""

