"""
src/document_processor/processor.py

Document processor with continuous ID tracking and append mode.
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import fitz
import tiktoken
from langchain.chat_models import init_chat_model
from langchain.prompts import ChatPromptTemplate
from langchain_text_splitters import RecursiveCharacterTextSplitter
from llama_cloud_services import LlamaParse
from loguru import logger
from pydantic import BaseModel, Field
from tqdm import tqdm

# ============================================================================
# MODELS & PROMPTS
# ============================================================================


class OutputResponse(BaseModel):
    """Represents a structured response containing contextual information and a flag indicating if it's a header."""

    response: str = Field(..., description="contextual document")
    is_header: bool = Field(..., description="Flag indicating if the response is a header.")


INSTRUCTION = """
The provided document is a company's annual report containing text in both English and Indonesian.

# TASK
- Extract relevant data exclusively from the English sections.
- If there is no English section, extract the Indonesian language or translate.

Ensure accuracy and present the information clearly in a structured format, such as bullet points, without summarizing or interpreting the content.
"""

SYSTEM_PROMPT = ChatPromptTemplate.from_template("""
You are an Investment Manager who specializes in financial analysis, specifically for Indonesian stocks. Your job is to provide brief and relevant context for the snippets of text from the stock's annual report.

<company_name>
{company_name}
</company_name>

<document>
{document}
</document>

Here is the chunk we want to situate within the whole document
<chunk>
{chunk}
</chunk>

Provide a concise context (1-3 sentences) considering these guidelines:
1. Identify the company name (MUST), financial metric/topic discussed (revenue, ROE, debt ratio, cash flow, total assets, etc.)
2. Specify the reporting period (Q1/Q2/Q3/Q4 2023, FY 2022, etc.) and any comparisons (YoY, QoQ)
3. Note the business segment if applicable (banking, telecommunications, consumer goods, etc.)
4. If relevant, mention how this relates to company's overall performance, strategy, or Indonesian market position
5. Do not use phrases such as "This section discusses" or "This section provides". Instead, state the context directly.

Please give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk. Answer only with the succinct context and nothing else.
""")


def count_tokens(text: str, model_name: str = "gpt-3.5-turbo") -> int:
    """Helper to count tokens using tiktoken encoder."""
    encoding = tiktoken.encoding_for_model(model_name)
    return len(encoding.encode(text))


# ============================================================================
# DOCUMENT PROCESSOR
# ============================================================================


class DocumentProcessor:
    """
    Enhanced document processor with continuous ID tracking and append mode.

    Key Features:
    - Automatic ID generation starting from last ID
    - Append mode: adds new chunks to existing JSON file
    - Preserves existing data structure
    """

    def __init__(
        self,
        instruction: str = INSTRUCTION,
        system_prompt: ChatPromptTemplate = SYSTEM_PROMPT,
        parse_mode: str = "parse_page_with_agent",
        model: str = "openai-gpt-4-1-mini",
        llm_contextual: str = "google",
        llama_parse_key: str = None,
    ) -> None:
        """
        Initialize the DocumentProcessor with configuration.

        Args:
            instruction: Custom instruction for LlamaParse
            system_prompt: Prompt template for contextual enrichment
            parse_mode: LlamaParse parsing mode
            model: LlamaParse model to use
            llm_contextual: LLM provider for contextual enrichment
            llama_parse_key: LlamaParse API key
        """
        self.llm_contextual = system_prompt | self._init_llm(llm_contextual).with_structured_output(
            OutputResponse
        )
        self.parser = self._init_parser(instruction, parse_mode, model, llama_parse_key)
        self.reset_stats()

    def _init_llm(self, llm_type: str):
        """Initialize the LLM for contextual enrichment."""
        if llm_type == "google":
            logger.info("Using Google gemini-2.5-flash...")
            return init_chat_model("gemini-2.5-flash", model_provider="google_genai")

        logger.info("Using Google openai/gpt-oss-20b...")
        return init_chat_model("openai/gpt-oss-20b", model_provider="groq")

    def _init_parser(self, instruction: str, parse_mode: str, model: str, api_key: str):
        """Initialize LlamaParse document parser."""
        logger.info("Initializing parser...")
        return LlamaParse(
            api_key=api_key,
            num_workers=4,
            verbose=True,
            language="en",
            user_prompt=instruction,
            parse_mode=parse_mode,
            model=model,
            high_res_ocr=True,
        )

    def reset_stats(self):
        """Reset processing statistics."""
        logger.info("Resetting processing stats...")
        self.stats = {"processed": 0, "success": 0, "failed": 0}

    def _load_existing_data(self, output_path: Path) -> tuple[list[dict], int]:
        """
        Load existing JSON data and get last ID.

        Returns:
            tuple: (existing_chunks, last_id)
        """
        if output_path.exists():
            logger.info(f"Loading existing data from {output_path}")
            with open(output_path, encoding="utf-8") as f:
                existing_data = json.load(f)

            # Find the highest ID
            last_id = 0
            if existing_data:
                last_id = max(chunk.get("id", 0) for chunk in existing_data)

            # Count by ticker
            ticker_counts = {}
            for chunk in existing_data:
                ticker = chunk.get("metadata", {}).get("tickers", "unknown")
                ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1

            logger.info(f"Loaded {len(existing_data)} existing chunks, last ID: {last_id}")
            logger.info(f"Breakdown by ticker: {ticker_counts}")
            return existing_data, last_id
        else:
            logger.info("No existing data found, starting fresh")
            return [], 0

    async def run_pipeline(
        self,
        input_file: str,
        company_name: str,
        tickers: str,
        output_file: str,
        output_filename: str = "ALL_DATA.json",
        start_page: int | None = None,
        end_page: int | None = None,
        mode: str = "append",
    ):
        """
        Execute the complete document processing pipeline.

        Args:
            input_file: Path to input PDF file
            company_name: Name of the company
            tickers: Stock ticker symbol(s)
            output_file: Output directory path
            output_filename: Name of output JSON file (default: ALL_DATA.json)
            start_page: Optional starting page (1-indexed)
            end_page: Optional ending page (1-indexed)
            mode: "append" or "new" (default: append)

        Returns:
            ProcessingResult with status and statistics
        """
        start_time = datetime.now()

        try:
            logger.info(f"🚀 Processing {input_file} in {mode.upper()} mode...")

            # Extract pages if range specified
            if start_page and end_page:
                input_file = self.extract_pages(input_file, start_page, end_page)

            # Process document
            md_content = await self.extract_content(input_file)
            json_data = self.convert_to_json(
                md_content, tickers, company_name, start_page, end_page
            )
            chunks = self.split_chunks(json_data)
            contextual_data = await self.add_context(chunks)

            # Save with ID tracking
            output_path = self.save_output(contextual_data, output_file, output_filename, mode=mode)

            # Update stats
            self.stats["success"] += 1
            logger.success(f"Document processed successfully → {output_path}")
            return self.create_result(True, str(output_path), start_time)

        except Exception as e:
            logger.error(f"Error processing document: {e}")
            self.stats["failed"] += 1
            return self.create_result(False, str(e), start_time)

    def extract_pages(self, input_file: str, start_page: int, end_page: int) -> str:
        """Extract specific page range from PDF."""
        logger.info(f"Extracting pages {start_page} to {end_page}...")
        output_file = f"temp_{Path(input_file).stem}_{start_page}_{end_page}.pdf"

        with fitz.open(input_file) as doc:
            new_doc = fitz.open()
            for page_num in range(start_page - 1, end_page):
                new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
            new_doc.save(output_file)

        return output_file

    async def extract_content(self, input_file: str):
        """Extract content from PDF using LlamaParse."""
        try:
            raw_content = await self.parser.aparse(input_file)
            logger.success("Document parsed successfully")
            return raw_content.get_markdown_documents(split_by_page=True)
        except Exception as e:
            logger.error(f"Error parsing document: {e}")
            raise Exception(f"Error extracting content: {e}") from e

    def convert_to_json(
        self, markdown_content, tickers: str, company_name: str, start_page: int, end_page: int
    ):
        """Convert markdown to JSON with metadata."""
        logger.info("Converting markdown to JSON...")
        json_data = []

        for i, doc in enumerate(markdown_content):
            actual_page = start_page + i if start_page else doc.metadata.get("page_number", i + 1)

            metadata = doc.metadata.copy()
            metadata.update(
                {"tickers": tickers, "company_name": company_name, "page_number": actual_page}
            )

            json_data.append({"text": doc.text, "metadata": metadata})

        return json_data

    def split_chunks(self, data: list[dict]):
        """Split text into chunks and filter by token count."""
        text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            model_name="gpt-3.5-turbo",
            chunk_size=512,
            chunk_overlap=100,
            separators=["\n\n", "\n", ".", " ", ""],
        )

        chunks = []
        logger.info("Splitting text into chunks...")

        for item in data:
            chunk_texts = text_splitter.split_text(item["text"])

            for chunk in chunk_texts:
                token_count = count_tokens(chunk)

                if token_count >= 64:
                    chunks.append(
                        {
                            "chunk_text": chunk,
                            "text": item["text"],
                            "metadata": item["metadata"],
                            "token_count": token_count,
                        }
                    )
                else:
                    logger.warning(f"Skipping chunk with {token_count} tokens")

        logger.success(f"Generated {len(chunks)} valid chunks")
        return chunks

    async def add_context(self, chunks: list[dict]):
        """Add contextual information to chunks using LLM."""
        contextual_data = []
        logger.info("Adding context to chunks...")

        try:
            for chunk in tqdm(chunks, desc="Adding context"):
                response = await self.llm_contextual.ainvoke(
                    {
                        "company_name": chunk["metadata"]["company_name"],
                        "document": chunk["text"],
                        "chunk": chunk["chunk_text"],
                    }
                )

                contextual_data.append(
                    {**chunk, "contextual_text": response.response, "is_header": response.is_header}
                )

                await asyncio.sleep(2)  # Rate limiting

            return contextual_data

        except Exception as e:
            logger.error(f"Error adding context: {e}")
            raise Exception(f"Error adding context: {e}") from e

    def save_output(
        self,
        new_data: list[dict],
        output_file: str,
        output_filename: str = "ALL_DATA.json",
        mode: str = "append",
    ) -> Path:
        """
        Save data with ID tracking and append mode support.

        Args:
            new_data: New chunks to save
            output_file: Output directory path
            output_filename: Name of output JSON file (default: ALL_DATA.json)
            mode: "append" or "new"

        Returns:
            Path to saved file
        """
        logger.info(f"Saving output in {mode.upper()} mode...")

        output_path = Path(output_file)
        output_path.mkdir(parents=True, exist_ok=True)
        final_file = output_path / output_filename

        if mode == "append":
            existing_data, last_id = self._load_existing_data(final_file)
        else:
            logger.info("Starting fresh (NEW mode)")
            existing_data, last_id = [], 0

        new_ticker = new_data[0]["metadata"]["tickers"] if new_data else "unknown"
        for i, chunk in enumerate(new_data, start=1):
            chunk["id"] = last_id + i

        combined_data = existing_data + new_data

        with open(final_file, "w", encoding="utf-8") as f:
            json.dump(combined_data, f, indent=4, ensure_ascii=False)

        logger.success(
            f"Saved {len(new_data)} new chunks for {new_ticker} "
            f"(Total: {len(combined_data)}, Last ID: {last_id + len(new_data)})"
        )

        return final_file

    def create_result(self, success: bool, data: Any, start_time: datetime):
        """Create standardized processing result."""
        result = {
            "status": "COMPLETED" if success else "FAILED",
            "execution_time": (datetime.now() - start_time).total_seconds(),
            "stats": self.stats.copy(),
        }

        if success:
            result["data"] = data
        else:
            result["error"] = data

        return result
