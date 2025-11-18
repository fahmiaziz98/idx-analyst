import argparse
import asyncio
import sys
from pathlib import Path
from loguru import logger
from dotenv import load_dotenv
import os

from processor import DocumentProcessor


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Document Processor with Continuous ID Tracking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process PDF from data/reports/ and save to data/processed/
  python cli.py --input data/reports/ADRO_2023.pdf --ticker ADRO --company "PT Adaro Energy"
  
  # Custom input/output paths
  python cli.py --input /path/to/report.pdf --ticker BBCA --company "Bank Central Asia" --output data/output
  
  # Process specific pages
  python cli.py --input data/reports/TLKM.pdf --ticker TLKM --company "Telkom Indonesia" --start-page 10 --end-page 20
  
  # Start fresh (overwrite existing data)
  python cli.py --input data/reports/ASII.pdf --ticker ASII --company "Astra International" --mode new
        """
    )
    
    # Required arguments
    parser.add_argument(
        '--input',
        type=str,
        required=True,
        help='Path to input PDF file (e.g., data/reports/ADRO.pdf or ./report.pdf)'
    )
    
    parser.add_argument(
        '--ticker',
        type=str,
        required=True,
        help='Stock ticker symbol (e.g., ADRO, BBCA, TLKM)'
    )
    
    parser.add_argument(
        '--company',
        type=str,
        required=True,
        help='Company name (e.g., "PT Adaro Energy")'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default='data/processed',
        help='Output directory path (default: data/processed)'
    )
    
    # Optional arguments
    parser.add_argument(
        '--output-filename',
        type=str,
        default='ALL_DATA.json',
        help='Output JSON filename (default: ALL_DATA.json)'
    )
    parser.add_argument(
        '--start-page',
        type=int,
        default=None,
        help='Starting page number (1-indexed, inclusive)'
    )
    
    parser.add_argument(
        '--end-page',
        type=int,
        default=None,
        help='Ending page number (1-indexed, inclusive)'
    )
    
    parser.add_argument(
        '--mode',
        type=str,
        choices=['append', 'new'],
        default='append',
        help='Processing mode: "append" (default) adds to existing data, "new" starts fresh'
    )
    
    parser.add_argument(
        '--llm',
        type=str,
        choices=['google', 'groq'],
        default='google',
        help='LLM provider for contextual enrichment (default: google)'
    )
    
    parser.add_argument(
        '--parse-mode',
        type=str,
        default='parse_page_with_agent',
        help='LlamaParse parsing mode (default: parse_page_with_agent)'
    )
    
    parser.add_argument(
        '--parse-model',
        type=str,
        default='openai-gpt-4-1-mini',
        help='LlamaParse model (default: openai-gpt-4-1-mini)'
    )
    
    return parser.parse_args()


def validate_arguments(args):
    """Validate parsed arguments."""
    errors = []
    
    if not Path(args.input).exists():
        errors.append(f"Input file not found: {args.input}")
    
    if not args.input.lower().endswith('.pdf'):
        errors.append(f"Input file must be a PDF: {args.input}")
    
    if args.start_page and args.end_page:
        if args.start_page > args.end_page:
            errors.append(f"start-page ({args.start_page}) must be <= end-page ({args.end_page})")
        if args.start_page < 1:
            errors.append(f"start-page must be >= 1")
    
    if (args.start_page and not args.end_page) or (args.end_page and not args.start_page):
        errors.append("Both --start-page and --end-page must be provided together")
    
    if len(args.ticker) > 10:
        logger.warning(f"Ticker '{args.ticker}' seems unusually long")
    
    if errors:
        logger.error("❌ Validation errors:")
        for error in errors:
            logger.error(f"  • {error}")
        sys.exit(1)


async def main():
    """Main CLI entry point."""
    # Setup
    load_dotenv()
    
    # Parse and validate arguments
    args = parse_arguments()
    validate_arguments(args)
    
    # Display configuration
    logger.info("=" * 80)
    logger.info("📋 Document Processing Configuration")
    logger.info("=" * 80)
    logger.info(f"Input File    : {args.input}")
    logger.info(f"Company       : {args.company}")
    logger.info(f"Ticker        : {args.ticker}")
    logger.info(f"Output Dir    : {args.output}")
    logger.info(f"Output File   : {args.output_filename}")
    logger.info(f"Mode          : {args.mode.upper()}")
    
    if args.start_page and args.end_page:
        logger.info(f"Page Range    : {args.start_page} - {args.end_page}")
    else:
        logger.info(f"Page Range    : ALL PAGES")
    
    logger.info(f"LLM Provider  : {args.llm}")
    logger.info(f"Parse Mode    : {args.parse_mode}")
    logger.info("=" * 80)
    
    # Check API keys
    llama_parse_key = os.getenv("LLAMA_PARSE_KEY")
    if not llama_parse_key:
        logger.error("❌ LLAMA_PARSE_KEY not found in environment variables")
        sys.exit(1)
    
    try:
        # Initialize processor
        logger.info("🔧 Initializing document processor...")
        processor = DocumentProcessor(
            llm_contextual=args.llm,
            parse_mode=args.parse_mode,
            model=args.parse_model,
            llama_parse_key=llama_parse_key
        )
        
        # Run pipeline
        result = await processor.run_pipeline(
            input_file=args.input,
            company_name=args.company,
            tickers=args.ticker,
            output_file=args.output,
            output_filename=args.output_filename,
            start_page=args.start_page,
            end_page=args.end_page,
            mode=args.mode
        )
        
        # Display results
        logger.info("=" * 80)
        logger.info("📊 Processing Results")
        logger.info("=" * 80)
        logger.info(f"Status        : {result['status']}")
        logger.info(f"Execution Time: {result['execution_time']:.2f} seconds")
        logger.info(f"Stats         : {result['stats']}")
        
        if result['status'] == 'COMPLETED':
            logger.info(f"Output File   : {result['data']}")
            logger.success("✅ Processing completed successfully!")
        else:
            logger.error(f"Error         : {result['error']}")
            logger.error("❌ Processing failed!")
            sys.exit(1)
        
        logger.info("=" * 80)
        
    except KeyboardInterrupt:
        logger.warning("⚠️ Processing interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.exception(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())