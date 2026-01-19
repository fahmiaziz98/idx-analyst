# AI-Document-Parsing (Experimental)

**AI-Document-Parsing** is an advanced pipeline designed for intelligent financial document processing, specifically tailored for Annual Reports. This tool leverages the power of **Multimodal Large Language Models (VLM)** to extract structured content and **LLMs** to provide deep contextual insights for complex financial tables.

## 🚀 Core Technologies

- **Multimodal VLM (Qwen3-VL-8B-Instruct)**: The primary engine for document-to-markdown conversion, processing page images with high accuracy.
- **PyMuPDF (fitz)**: Handles high-fidelity PDF rasterization with built-in auto-rotation support.
- **OpenCV & Pillow**: Powering image pre-processing, orientation correction, and intelligent whitespace cropping.
- **LangChain & Tiktoken**: Optimized token-based chunking strategy for seamless RAG (Retrieval-Augmented Generation) integration.
- **OpenAI-Compatible SDK**: A standardized interface for seamless communication with VLM/LLM endpoints.
- **Pydantic Settings**: Robust environment and configuration management.

## 📂 Project Structure

```text
ai_parsing/
├── ai_parsing/             # Core Python Package
│   ├── core/               # Configuration and exception handling
│   ├── pipeline/           # Processing logic (Parser, Chunker, Contextualizer)
│   ├── utils/              # Helper functions (Timing, Logging)
│   ├── cli.py              # Command Line Interface
│   ├── processor.py        # Pipeline orchestrator
│   ├── schemas.py          # Pydantic data models
│   ├── __main__.py         # Package entry point for 'python -m'
│   └── __init__.py
├── pyproject.toml          # Dependency management (UV/PIP)
├── README.md               # Main documentation
└── .env                    # Environment variables (API Keys, Endpoints)
```

## 🛠️ Installation

This project utilizes [uv](https://github.com/astral-sh/uv) for lightning-fast package management.

1.  **Clone the repository** and navigate to the application directory:
    ```bash
    cd apps/ai_parsing
    ```

2.  **Install dependencies**:
    ```bash
    uv sync
    ```

3.  **Environment Setup**:
    Create a `.env` file based on `.env.example`:
    ```bash
    VLLM_ENDPOINT="your_vllm_endpoint_here"
    OPENAI_API_KEY="your_key_if_needed"
    ```

## 📖 Usage

You can run the application directly using the Python module runner:

### CLI Help
```bash
python3 -m ai_parsing --help
```

### Processing a Document
```bash
python3 -m ai_parsing \
  --input "data/reports/ADRO_2023.pdf" \
  --ticker "ADRO" \
  --company "PT Adaro Energy" \
  --year 2023
```

### Advanced Options
- `--start-page` & `--end-page`: Process a specific range of pages.
- `--no-contextualization`: Disable table contextualization (faster & saves tokens).
- `--mode new`: Overwrite existing data and create a fresh output file.
- `--verbose`: Enable detailed debug logging.

## 💡 Key Features

- **Intelligent Table Context**: Financial tables are often cryptic without context. This feature automatically generates a summary of table contents based on the surrounding page context.
- **Multimodal Integration**: Uses **Qwen3-VL-8B-Instruct** to "see" the document, ensuring layout-aware extraction that beats traditional OCR.
- **Auto-Orientation**: Automatically detects and corrects rotated or tilted pages before processing.
- **Smart Cropping**: Removes unnecessary white margins to help the VLM focus on actual content.
- **Deterministic Chunk IDs**: Generates consistent UUIDs based on content hashing, preventing duplicates in vector databases.

---
Developed with ❤️ for advanced financial data analysis.
