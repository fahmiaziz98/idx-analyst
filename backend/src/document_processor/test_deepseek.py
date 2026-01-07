import asyncio
import base64
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Literal
from io import BytesIO

import aiofiles
from openai import AsyncOpenAI
from pdf2image import convert_from_path
from PIL import Image, ImageOps

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())


class MarkdownCleanupAgent:
    """
    LLM-powered markdown structure cleanup agent
    
    Based on research findings:
    - Markdown is preferred format for LLMs (token efficient, readable)
    - Preserve ALL original data/numbers (no hallucination)
    - Only fix structure issues (headers, lists, tables)
    - Fast models (Groq/Kimi) optimal for this task
    """
    
    # System prompt optimized for Indonesian financial statements
    SYSTEM_PROMPT = """You are a markdown structure cleanup specialist for FINANCIAL STATEMENTS. Your ONLY job is to fix markdown formatting while preserving ALL original data exactly as-is.

# CRITICAL RULES (MUST FOLLOW):
1. **PRESERVE ALL DATA**: Do NOT change any numbers, dates, names, or factual content
2. **NO ADDITIONS**: Do not add explanations, summaries, or new information
3. **NO REMOVALS**: Do not remove any content, even if it seems redundant
4. **STRUCTURE ONLY**: Only fix markdown syntax (tables, headers, lists)

# MAIN FOCUS - FINANCIAL TABLE NORMALIZATION:

## Correct Table Format:
Financial statement tables MUST have consistent structure:

```
| deskripsi          | catatan/notes | 2024 | 2023 | Description
|--------------------|---------------|------|------|---------
| kas dan setara kas | 5             | 4,751,621 | 9,208,814 | Cash and cash equivalents
| piutang dagang     | 6             | 943,915 | 1,091,901 | Trade receivables
```

## Table Rules:
1. **Consistent column count** - Every row MUST have the same number of columns
2. **Sub-items with indent** - Use "- " prefix for sub-categories:
   ```
   | Prepaid taxes | 19a | | |
   | - Corporate income tax | | 724,916 | 329,412 |
   | - Other taxes | | 14,502 | 29,936 |
   ```
3. **Bold for totals** - Total/subtotal rows use **bold**:
   ```
   | **Total current assets** | | **17,991,975** | **20,064,546** |
   ```
4. **Empty cells must exist** - If no value, keep empty cell: `| | |`
5. **Bilingual content** - If both Indonesian and English present, keep as separate columns or sections

## MUST Fix:
- Table rows with inconsistent column counts
- Numbers separated from their labels (merge to correct row)
- Missing or incomplete table headers
- Excessive newlines within tables

## MUST NOT Change:
- All numbers, amounts, percentages
- Account names (Kas, Piutang, Persediaan, Cash, Receivables, etc.)
- Note references (5, 6, 7, 19a, etc.)
- Currency formats (IDR, rupiah, juta, ribu, millions)

# OUTPUT:
- Return ONLY the cleaned markdown
- NO preamble ("Here is the cleaned version...")
- NO postamble ("I've fixed the formatting...")
- Start directly with the content

Remember: Your ONLY job is structure cleanup. PRESERVE ALL original content."""

    def __init__(
        self,
        base_url: str = "https://api.groq.com/openai/v1",
        model: str = "moonshotai/kimi-k2-instruct-0905",
        api_key: Optional[str] = None,
        timeout: int = 300
    ):
        """
        Initialize cleanup agent
        
        Args:
            base_url: API base URL (Groq recommended)
            model: Model name (fast models preferred)
            api_key: API key (or set GROQ_API_KEY env var)
            timeout: Request timeout
        """
        self.model = model
        
        # Get API key from env if not provided
        if api_key is None:
            import os
            api_key = os.getenv("GROQ_API_KEY")
        
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout
        )
        
        print(f"  Cleanup Agent: {model}")
    
    async def cleanup(self, raw_markdown: str) -> Dict[str, any]:
        """
        Clean up markdown structure
        
        Args:
            raw_markdown: Raw OCR output
        
        Returns:
            Dict with cleaned_text, original_length, cleaned_length
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": raw_markdown}
                ],
                temperature=0.0,  # Deterministic
                max_tokens=8192,
            )
            
            cleaned = response.choices[0].message.content.strip()
            
            return {
                "cleaned_text": cleaned,
                "original_length": len(raw_markdown),
                "cleaned_length": len(cleaned),
                "tokens_used": response.usage.total_tokens if hasattr(response, 'usage') else 0
            }
        
        except Exception as e:
            print(f"  ⚠️  Cleanup failed: {e}")
            # Fallback to original
            return {
                "cleaned_text": raw_markdown,
                "original_length": len(raw_markdown),
                "cleaned_length": len(raw_markdown),
                "tokens_used": 0,
            }


class DeepseekOcrClient:
    """
    Production-ready async client with optional markdown cleanup
    """
    
    # Task templates
    TASKS = {
        "markdown": {
            "prompt": "<image>\nConvert the document to markdown.",
            "description": "Convert to structured markdown"
        },
        "free_ocr": {
            "prompt": "<image>\nFree OCR.",
            "description": "Simple text extraction"
        },
        "locate": {
            "prompt": "<image>\nLocate <|ref|>{ref}<|/ref|> in the image.",
            "description": "Find specific text/object"
        },
        "describe": {
            "prompt": "<image>\nDescribe this image in detail.",
            "description": "Image description"
        },
        "parse_figure": {
            "prompt": "<image>\nParse the figure.",
            "description": "Extract chart/graph data"
        }
    }
    
    MODES = {
        "tiny": {"description": "512×512 - Fastest"},
        "small": {"description": "640×640 - Quick"},
        "base": {"description": "1024×1024 - Standard"},
        "large": {"description": "1280×1280 - High quality"},
        "gundam": {"description": "Multi-tile - Best for complex docs"}
    }
    
    def __init__(
        self,
        api_url: str,
        model_name: str = "deepseek-ocr",
        mode: Literal["tiny", "small", "base", "large", "gundam"] = "gundam",
        task: Literal["markdown", "free_ocr", "locate", "describe", "parse_figure"] = "markdown",
        enable_cleanup: bool = False,
        cleanup_model: str = "llama-3.3-70b-versatile",
        groq_api_key: Optional[str] = None,
        timeout: int = 600
    ):
        """
        Initialize client
        
        Args:
            api_url: DeepSeek-OCR API URL
            model_name: Model name
            mode: Resolution mode
            task: Default task
            enable_cleanup: Enable LLM markdown cleanup
            cleanup_model: Groq model for cleanup
            groq_api_key: Groq API key (or env GROQ_API_KEY)
            timeout: Request timeout
        """
        self.mode = mode
        self.task = task
        self.model_name = model_name
        self.enable_cleanup = enable_cleanup
        
        # OCR client
        self.client = AsyncOpenAI(
            api_key="EMPTY",
            base_url=api_url,
            timeout=timeout
        )
        
        # Cleanup agent (optional)
        if enable_cleanup:
            self.cleanup_agent = MarkdownCleanupAgent(
                model=cleanup_model,
                api_key=groq_api_key
            )
        else:
            self.cleanup_agent = None
        
        print(f"✅ Client initialized")
        print(f"   OCR API: {api_url}")
        print(f"   Mode: {mode} - {self.MODES[mode]['description']}")
        print(f"   Task: {task} - {self.TASKS[task]['description']}")
        print(f"   Cleanup: {'Enabled' if enable_cleanup else 'Disabled'}")
    
    def _preprocess_image(self, image: Image.Image, dpi: int = 300) -> Image.Image:
        """Minimal preprocessing (Gradio-style)"""
        if image.mode in ('RGBA', 'LA', 'P'):
            image = image.convert('RGB')
        
        image = ImageOps.exif_transpose(image)
        
        width, height = image.size
        min_width = int(8.5 * dpi)
        
        if width < min_width:
            scale = min_width / width
            new_size = (int(width * scale), int(height * scale))
            image = image.resize(new_size, Image.Resampling.BICUBIC)
        
        return image
    
    def _clean_grounding(self, text: str) -> str:
        """Remove grounding annotations"""
        import re
        
        if not text:
            return ""
        
        pattern = r'<\|ref\|>.*?<\|/ref\|><\|det\|>.*?<\|/det\|>'
        text = re.sub(pattern, '', text, flags=re.DOTALL)
        
        lines = [line for line in text.split('\n') if line.strip()]
        
        return '\n'.join(lines).strip()
    
    async def extract_text(
        self,
        image: Image.Image,
        task: Optional[str] = None,
        ref_text: Optional[str] = None
    ) -> tuple[str, Optional[Dict]]:
        """
        Extract text from image
        
        Returns:
            Tuple of (text, cleanup_info)
        """
        task = task or self.task
        
        # Build prompt
        if task == "locate":
            if not ref_text:
                raise ValueError("ref_text required for locate task")
            prompt = self.TASKS[task]["prompt"].format(ref=ref_text)
        else:
            prompt = self.TASKS[task]["prompt"]
        
        # Convert to base64
        buffer = BytesIO()
        image.save(buffer, format='JPEG', quality=95)
        image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        # Call OCR API
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    },
                    {"type": "text", "text": prompt}
                ]
            }],
            max_tokens=4096,
            temperature=0.0,
            extra_body={
                "skip_special_tokens": False,
                "vllm_xargs": {
                    "ngram_size": 30,
                    "window_size": 90,
                }
            }
        )
        
        text = response.choices[0].message.content
        text = self._clean_grounding(text)
        
        # Optional: Cleanup with LLM
        cleanup_info = None
        if self.enable_cleanup and task == "markdown":
            cleanup_result = await self.cleanup_agent.cleanup(text)
            text = cleanup_result["cleaned_text"]
            cleanup_info = {
                "original_length": cleanup_result["original_length"],
                "cleaned_length": cleanup_result["cleaned_length"],
                "tokens_used": cleanup_result.get("tokens_used", 0),
            }
        
        return text, cleanup_info
    
    async def process_image(
        self,
        image_path: str,
        dpi: int = 300,
        task: Optional[str] = None,
        ref_text: Optional[str] = None
    ) -> Dict:
        """Process single image"""
        print(f"\n{'='*80}")
        print(f"Processing: {image_path}")
        print(f"{'='*80}")
        
        image = Image.open(image_path)
        original_size = image.size
        print(f"Original: {original_size}")
        
        image = self._preprocess_image(image, dpi)
        preprocessed_size = image.size
        print(f"Preprocessed: {preprocessed_size}")
        
        task_type = task or self.task
        print(f"Running OCR (mode: {self.mode}, task: {task_type})...")
        
        text, cleanup_info = await self.extract_text(image, task, ref_text)
        
        print(f"✅ Extracted {len(text)} characters")
        if cleanup_info:
            print(f"  Cleanup: {cleanup_info['original_length']} → {cleanup_info['cleaned_length']} chars")
        
        metadata = {
            "model_name": f"deepseek-ocr-{self.mode}",
            "date": datetime.now().isoformat(),
            "file_name": Path(image_path).name,
            "resolution_mode": self.mode,
            "task_type": task_type,
            "preprocessing_dpi": dpi,
            "character_count": len(text),
            "image_dimensions": {
                "original": {"width": original_size[0], "height": original_size[1]},
                "preprocessed": {"width": preprocessed_size[0], "height": preprocessed_size[1]}
            }
        }
        
        if cleanup_info:
            metadata["cleanup"] = cleanup_info
        
        return {
            "raw_text": text,
            "metadata": metadata
        }
    
    async def process_pdf(
        self,
        pdf_path: str,
        dpi: int = 300,
        start_page: int = 1,
        end_page: Optional[int] = None,
        task: Optional[str] = None,
        batch_size: int = 5
    ) -> List[Dict]:
        """Process PDF with batching"""
        print(f"\n{'='*80}")
        print(f"Processing PDF: {pdf_path}")
        print(f"{'='*80}")
        
        print(f"Converting PDF at {dpi} DPI...")
        images = convert_from_path(pdf_path, dpi=dpi, fmt='jpeg')
        total_pages = len(images)
        
        print(f"Total pages: {total_pages}")
        
        if end_page is None:
            end_page = total_pages
        
        images = images[start_page-1:end_page]
        print(f"Processing pages {start_page}-{end_page} ({len(images)} pages)")
        print(f"Batch size: {batch_size} concurrent requests")
        
        results = []
        
        for batch_start in range(0, len(images), batch_size):
            batch_end = min(batch_start + batch_size, len(images))
            batch = images[batch_start:batch_end]
            
            print(f"\n{'='*80}")
            print(f"Batch {batch_start//batch_size + 1}: Pages {start_page + batch_start}-{start_page + batch_end - 1}")
            print(f"{'='*80}")
            
            tasks = []
            for idx, image in enumerate(batch):
                page_num = start_page + batch_start + idx
                
                original_size = image.size
                image = self._preprocess_image(image, dpi)
                preprocessed_size = image.size
                
                task_coro = self._process_single_page(
                    image, page_num, total_pages,
                    Path(pdf_path).stem, task,
                    original_size, preprocessed_size, dpi
                )
                tasks.append(task_coro)
            
            batch_results = await asyncio.gather(*tasks)
            results.extend(batch_results)
            
            print(f"✅ Batch complete ({len(batch_results)} pages)")
        
        print(f"\n{'='*80}")
        print(f"✅ PDF processing complete!")
        print(f"Total pages: {len(results)}")
        print(f"Total characters: {sum(r['metadata']['character_count'] for r in results)}")
        print(f"{'='*80}")
        
        return results
    
    async def _process_single_page(
        self,
        image: Image.Image,
        page_num: int,
        total_pages: int,
        pdf_stem: str,
        task: Optional[str],
        original_size: tuple,
        preprocessed_size: tuple,
        dpi: int
    ) -> Dict:
        """Process single page"""
        print(f"  Page {page_num}: Processing...")
        
        text, cleanup_info = await self.extract_text(image, task)
        
        print(f"  Page {page_num}: ✅ {len(text)} chars")
        if cleanup_info:
            print(f"  Page {page_num}: Cleanup {cleanup_info['original_length']} → {cleanup_info['cleaned_length']}")
        
        metadata = {
            "model_name": f"deepseek-ocr-{self.mode}",
            "date": datetime.now().isoformat(),
            "file_name": f"{pdf_stem}_page_{page_num:04d}.jpg",
            "page_number": page_num,
            "total_pages": total_pages,
            "resolution_mode": self.mode,
            "task_type": task or self.task,
            "preprocessing_dpi": dpi,
            "character_count": len(text),
            "image_dimensions": {
                "original": {"width": original_size[0], "height": original_size[1]},
                "preprocessed": {"width": preprocessed_size[0], "height": preprocessed_size[1]}
            }
        }
        
        if cleanup_info:
            metadata["cleanup"] = cleanup_info
        
        return {
            "raw_text": text,
            "metadata": metadata
        }
    
    async def save_json(self, results: List[Dict], output_path: str):
        """Save results to JSON"""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        async with aiofiles.open(output_file, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(results, indent=2, ensure_ascii=False))
        
        print(f"\n{'='*80}")
        print("✅ Results saved!")
        print(f"{'='*80}")
        print(f"Output: {output_file}")
        print(f"Pages: {len(results)}")
        print(f"Total chars: {sum(r['metadata']['character_count'] for r in results)}")
        
        # Cleanup stats
        if any('cleanup' in r['metadata'] for r in results):
            total_cleanup_tokens = sum(
                r['metadata'].get('cleanup', {}).get('tokens_used', 0)
                for r in results
            )
            print(f"Cleanup tokens used: {total_cleanup_tokens:,}")
        
        print("="*80)


# CLI
async def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Async DeepSeek-OCR with optional markdown cleanup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic OCR
  python deepseek_cleanup.py --data-path report.pdf --api http://localhost:8000/v1 --output results.json
  
  # With LLM cleanup (recommended for markdown task)
  python deepseek_cleanup.py --data-path report.pdf --api http://localhost:8000/v1 --cleanup --output results.json
  
  # Custom cleanup model
  python deepseek_cleanup.py --data-path report.pdf --cleanup --cleanup-model llama-3.3-70b-versatile --output results.json

Cleanup Models (Groq):
  llama-3.3-70b-versatile  - Best balance (recommended)
  llama-3.1-70b-versatile  - Alternative
  mixtral-8x7b-32768       - Faster, lower quality
        """
    )
    
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--data-path", help="PDF file")
    input_group.add_argument("--image", help="Image file")
    
    parser.add_argument("--mode", choices=list(DeepseekOcrClient.MODES.keys()), default="gundam")
    parser.add_argument("--task", choices=list(DeepseekOcrClient.TASKS.keys()), default="markdown")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int)
    parser.add_argument("--batch", type=int, default=5)
    parser.add_argument("--output", required=True)
    
    # Cleanup options
    parser.add_argument("--cleanup", action="store_true", help="Enable LLM markdown cleanup")
    parser.add_argument("--cleanup-model", default="moonshotai/kimi-k2-instruct-0905", help="Groq model for cleanup")
    
    args = parser.parse_args()
    
    client = DeepseekOcrClient(
        api_url="https://fahmiaziz98--deepseek-ocr-server-serve.modal.run/v1",
        mode=args.mode,
        task=args.task,
        enable_cleanup=args.cleanup,
        cleanup_model=args.cleanup_model,
    )
    
    if args.data_path:
        results = await client.process_pdf(
            args.data_path,
            dpi=args.dpi,
            start_page=args.start,
            end_page=args.end,
            batch_size=args.batch
        )
    else:
        result = await client.process_image(args.image, dpi=args.dpi)
        results = [result]
    
    await client.save_json(results, args.output)


if __name__ == "__main__":
    asyncio.run(main())