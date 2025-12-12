#!/usr/bin/env python3
"""
Generate segments.json from a PDF without creating audio.
Fast way to prepare text analysis for later streaming.
"""

import os
import sys
import json
import logging
from dotenv import load_dotenv
from audio_reader import AudiobookReaderContinuous

# Configure logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger(__name__)


def generate_segments_only(pdf_path: str, output_dir: str = "output", language: str = "en") -> str:
    """
    Extract text from PDF, analyze with Gemini, and save segments.json.
    Does NOT generate any audio - just creates the JSON file.
    
    Returns:
        Path to the generated segments.json file
    """
    reader = AudiobookReaderContinuous()
    
    # Extract PDF filename
    pdf_basename = os.path.basename(pdf_path)
    pdf_name_without_ext = os.path.splitext(pdf_basename)[0]
    
    # Create output folder
    pdf_output_folder = os.path.join(output_dir, pdf_name_without_ext)
    os.makedirs(pdf_output_folder, exist_ok=True)
    logger.info(f"📁 Output folder: {pdf_output_folder}")
    
    # Extract text from PDF
    logger.info(f"📖 Extracting text from: {pdf_path}")
    text = reader.extract_text_from_pdf(pdf_path)
    logger.info(f"   Extracted {len(text)} characters")
    
    # Normalize text
    text = ' '.join(text.split())
    
    # Analyze with Gemini
    logger.info("🤖 Analyzing text with Gemini AI...")
    logger.info("   (This may take 30-60 seconds for longer texts)")
    segments_with_voices = reader.analyze_text_and_assign_voices_with_gemini(text, language=language)
    logger.info(f"   ✅ Created {len(segments_with_voices)} segments")
    
    # Save segments.json
    json_output_path = os.path.join(pdf_output_folder, "segments.json")
    with open(json_output_path, 'w', encoding='utf-8') as f:
        json.dump(segments_with_voices, f, indent=2, ensure_ascii=False)
    
    logger.info(f"💾 Saved segments to: {json_output_path}")
    
    return json_output_path


def main():
    """Main entry point"""
    load_dotenv()
    
    # Parse command line arguments
    if len(sys.argv) < 2:
        print("Usage: python generate_segments.py <pdf_path> [output_dir] [language]")
        print()
        print("Examples:")
        print('  python generate_segments.py "my-book.pdf"')
        print('  python generate_segments.py "my-book.pdf" "custom_output"')
        print('  python generate_segments.py "my-book.pdf" "output" "es"')
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "output"
    language = sys.argv[3] if len(sys.argv) > 3 else "en"
    
    # Validate PDF exists
    if not os.path.exists(pdf_path):
        logger.error(f"❌ PDF not found: {pdf_path}")
        sys.exit(1)
    
    logger.info("=" * 60)
    logger.info("📝 SEGMENTS.JSON GENERATOR")
    logger.info("=" * 60)
    logger.info(f"PDF: {pdf_path}")
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"Language: {language}")
    logger.info("=" * 60)
    
    try:
        # Generate segments
        json_path = generate_segments_only(pdf_path, output_dir, language)
        
        logger.info("=" * 60)
        logger.info("✅ SUCCESS!")
        logger.info("=" * 60)
        logger.info(f"📄 segments.json: {json_path}")
        logger.info("=" * 60)
        logger.info("")
        logger.info("🎵 Next step: Stream the audio!")
        logger.info(f'   python stream_player.py "{json_path}"')
        logger.info("")
        
    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"❌ ERROR: {e}")
        logger.error("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()

