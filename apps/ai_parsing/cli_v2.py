import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

from .core.exception import DocumentProcessorError
from .processor_v2 import DocumentProcessor


def setup_logging(verbose: bool = False):
    """
    Configure logging with loguru.

    Args:
        verbose: Enable debug-level logging
    """
    logger.remove()  # Remove default handler

    log_level = "DEBUG" if verbose else "INFO"

    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level=log_level,
        colorize=True,
    )


def parse_arguments():
    """
    Parse command-line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="Process financial PDFs with intelligent chunking and contextualization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage (process entire PDF)
  python -m apps.ai_parsing.cli_v2 \\
    --input data/reports/ADRO_2023.pdf \\
    --ticker ADRO \\
    --company "PT Adaro Energy" \\
    --year 2023

  # Process specific page range
  python -m apps.ai_parsing.cli_v2 \\
    --input data/reports/BBCA_2023.pdf \\
    --ticker BBCA \\
    --company "Bank Central Asia" \\
    --year 2023 \\
    --start-page 50 \\
    --end-page 75

  # Custom output location
  python -m apps.ai_parsing.cli_v2 \\
    --input data/reports/TLKM_2023.pdf \\
    --ticker TLKM \\
    --company "Telkom Indonesia" \\
    --year 2023 \\
    --output data/output \\
    --output-filename TLKM_2023.json

  # Start fresh (overwrite existing data)
  python -m apps.ai_parsing.cli_v2 \\
    --input data/reports/ASII_2023.pdf \\
    --ticker ASII \\
    --company "Astra International" \\
    --year 2023 \\
    --mode new

  # Disable table contextualization (faster, cheaper)
  python -m apps.ai_parsing.cli_v2 \\
    --input data/reports/UNVR_2023.pdf \\
    --ticker UNVR \\
    --company "Unilever Indonesia" \\
    --year 2023 \\
    --no-contextualization

Environment Variables:
  LLAMA_PARSE_KEY       LlamaParse API key (required)
  OPENAI_API_KEY        OpenAI-compatible API key for contextualization
  GROQ_API_KEY          Alternative to OPENAI_API_KEY
        """,
    )

    # Required arguments
    required = parser.add_argument_group("required arguments")

    required.add_argument("--input", type=str, required=True, help="Path to input PDF file")

    required.add_argument(
        "--ticker", type=str, required=True, help="Stock ticker symbol (e.g., ADRO, BBCA, TLKM)"
    )

    required.add_argument(
        "--company", type=str, required=True, help='Company name (e.g., "PT Adaro Energy")'
    )

    required.add_argument(
        "--year", type=int, required=True, help="Reporting year (e.g., 2023, 2024)"
    )

    # Optional arguments - Output
    output_group = parser.add_argument_group("output options")

    output_group.add_argument(
        "--output",
        type=str,
        default="data/processed",
        help="Output directory path (default: data/processed)",
    )

    output_group.add_argument(
        "--output-filename",
        type=str,
        default="processed_data.json",
        help="Output JSON filename (default: processed_data.json)",
    )

    output_group.add_argument(
        "--mode",
        type=str,
        choices=["append", "new"],
        default="append",
        help='"append" (default) adds to existing data, "new" starts fresh',
    )

    # Optional arguments - Processing
    processing_group = parser.add_argument_group("processing options")

    processing_group.add_argument(
        "--start-page", type=int, default=None, help="Starting page number (1-indexed, inclusive)"
    )

    processing_group.add_argument(
        "--end-page", type=int, default=None, help="Ending page number (1-indexed, inclusive)"
    )

    processing_group.add_argument(
        "--chunk-size", type=int, default=1024, help="Maximum tokens per chunk (default: 1024)"
    )

    processing_group.add_argument(
        "--chunk-overlap",
        type=int,
        default=150,
        help="Overlap tokens between chunks (default: 150)",
    )

    processing_group.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="DPI for image extraction (default: 300). Higher = better quality but slower.",
    )

    processing_group.add_argument(
        "--no-contextualization",
        action="store_true",
        help="Disable LLM contextualization for tables (faster, cheaper)",
    )

    # Optional arguments - Advanced
    advanced_group = parser.add_argument_group("advanced options")

    advanced_group.add_argument("--verbose", action="store_true", help="Enable debug logging")

    return parser.parse_args()


def validate_arguments(args):
    """
    Validate parsed arguments.

    Args:
        args: Parsed arguments namespace

    Raises:
        ValidationError: If validation fails
        SystemExit: On validation errors (exits with code 1)
    """
    errors = []

    # Validate input file
    if not Path(args.input).exists():
        errors.append(f"Input file not found: {args.input}")
    elif not args.input.lower().endswith(".pdf"):
        errors.append(f"Input file must be a PDF: {args.input}")

    # Validate year
    if args.year < 1900 or args.year > 2100:
        errors.append(f"Year must be between 1900-2100: {args.year}")

    # Validate page range
    if args.start_page and args.end_page:
        if args.start_page > args.end_page:
            errors.append(f"start-page ({args.start_page}) must be <= end-page ({args.end_page})")
        if args.start_page < 1:
            errors.append("start-page must be >= 1")

    if (args.start_page and not args.end_page) or (args.end_page and not args.start_page):
        errors.append("Both --start-page and --end-page must be provided together")

    # Validate chunking params
    if args.chunk_size < 64:
        errors.append(f"chunk-size must be >= 64: {args.chunk_size}")

    if args.chunk_overlap < 0:
        errors.append(f"chunk-overlap must be >= 0: {args.chunk_overlap}")

    if args.chunk_overlap >= args.chunk_size:
        errors.append(
            f"chunk-overlap ({args.chunk_overlap}) must be < chunk-size ({args.chunk_size})"
        )

    # Warnings
    if len(args.ticker) > 10:
        logger.warning(f"Ticker '{args.ticker}' seems unusually long")

    # Report errors
    if errors:
        logger.error("❌ Validation errors:")
        for error in errors:
            logger.error(f"  • {error}")
        sys.exit(1)


def check_environment_variables():
    """
    Check required environment variables for VLM.

    Returns:
        Dictionary with status of keys
    """
    vllm_endpoint = os.getenv("VLLM_ENDPOINT")
    vllm_api_key = os.getenv("VLLM_API_KEY")

    if not vllm_endpoint:
        logger.error("❌ VLLM_ENDPOINT not found in environment variables")
        logger.error("   Required for Vision-Language Model parsing (Qwen3-VL)")
        sys.exit(1)

    return {"vllm_endpoint": vllm_endpoint, "vllm_api_key": vllm_api_key}


def display_configuration(args, api_status: dict):
    """
    Display processing configuration.

    Args:
        args: Parsed arguments
        api_status: Dictionary with API configuration status
    """
    logger.info("=" * 80)
    logger.info("📋 Document Processing Configuration")
    logger.info("=" * 80)
    logger.info(f"Input File    : {args.input}")
    logger.info(f"Company       : {args.company}")
    logger.info(f"Ticker        : {args.ticker}")
    logger.info(f"Year          : {args.year}")
    logger.info(f"Output Dir    : {args.output}")
    logger.info(f"Output File   : {args.output_filename}")
    logger.info(f"Mode          : {args.mode.upper()}")

    if args.start_page and args.end_page:
        logger.info(f"Page Range    : {args.start_page} - {args.end_page}")
    else:
        logger.info("Page Range    : ALL PAGES")

    logger.info(f"Chunk Size    : {args.chunk_size} tokens")
    logger.info(f"Chunk Overlap : {args.chunk_overlap} tokens")
    logger.info(f"Image DPI     : {args.dpi}")

    # VLM Endpoint status
    logger.info(f"VLM Endpoint  : {api_status.get('vllm_endpoint')}")

    # Contextualization status
    if args.no_contextualization:
        logger.info("Context       : DISABLED")
    else:
        logger.info("Context       : ENABLED (tables only)")

    logger.info("=" * 80)


async def main():
    """
    Main CLI entry point.
    """
    # Load environment variables
    load_dotenv()

    # Parse arguments
    args = parse_arguments()

    # Setup logging
    setup_logging(verbose=args.verbose)

    # Validate arguments
    validate_arguments(args)

    # Check environment variables
    api_keys = check_environment_variables()

    # Display configuration
    display_configuration(args, api_keys)

    try:
        # Initialize processor
        logger.info("🔧 Initializing document processor...")

        processor = DocumentProcessor(
            enable_contextualization=not args.no_contextualization,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
            dpi=args.dpi,
        )

        # Process document
        result = await processor.process_document(
            input_file=args.input,
            company_name=args.company,
            ticker=args.ticker,
            year=args.year,
            output_dir=args.output,
            output_filename=args.output_filename,
            start_page=args.start_page or 1,
            end_page=args.end_page,
            mode=args.mode,
        )

        # Display results
        logger.info("=" * 80)
        logger.info("📊 Processing Results")
        logger.info("=" * 80)
        logger.info(f"Status        : {result.status}")

        if result.stats:
            logger.info(f"Total Chunks  : {result.stats.total_chunks}")
            logger.info(f"  - Tables    : {result.stats.table_chunks}")
            logger.info(f"  - Text      : {result.stats.text_chunks}")
            logger.info(f"Contextualized: {result.stats.contextualized_chunks}")
            logger.info(f"Processing    : {result.stats.processing_time:.2f}s")

        if result.status == "COMPLETED":
            logger.info(f"Output File   : {result.output_path}")
            logger.success("✅ Processing completed successfully!")
        else:
            logger.error(f"Error         : {result.error}")
            logger.error("❌ Processing failed!")
            sys.exit(1)

        logger.info("=" * 80)

        # Cleanup
        await processor.close()

    except KeyboardInterrupt:
        logger.warning("⚠️ Processing interrupted by user")
        sys.exit(130)
    except DocumentProcessorError as e:
        logger.error(f"❌ Processing error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
