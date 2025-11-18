# 🧠 IDX-Analyst
**Context-Aware RAG System for Indonesian Financial Reports**

> "Making sense of complex financial tables and documents shouldn't require hours of manual reading."

[![Status](https://img.shields.io/badge/status-MVP-yellow)]()
[![Python](https://img.shields.io/badge/python-3.11+-blue)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()

**Current Version:** 1.0.0 (MVP)

---
## Motivation

Indonesian stock market investors and analysts face a critical challenge: **extracting actionable insights from hundreds of pages of annual reports**. These documents contain vital information about company performance, but the data is often buried in:

- Complex financial tables spanning multiple pages
- Dense text mixing qualitative and quantitative information
- Technical accounting terminology and regulatory disclosures
- Inconsistent formatting across different companies

Traditional RAG systems struggle with financial documents because:
- **Standard chunking breaks table context**, making numerical data unretrievable
- **Semantic search fails on tabular data** where structure matters more than semantics
- **Lexical matching misses implicit relationships** between financial concepts

**IDX-Analyst** was built to solve these problems by introducing **contextual retrieval** specifically designed for structured financial documents.

---

## The Challenge

### Problem 1: Table Retrieval Failure
When financial tables are chunked into a vector database, queries like *"What is Bank BCA's total debt in 2023?"* often return **irrelevant results** because:

- Row/column relationships are destroyed during chunking
- Numbers lose their semantic meaning without headers
- Multi-page tables get fragmented across chunks

### Problem 2: Context Loss
Financial documents require understanding:
- Which company the data refers to
- Which fiscal year is being discussed  
- Which section of the report (Balance Sheet vs. Cash Flow)
- The relationship between multiple tables

Standard embedding models capture semantic similarity but **fail to preserve document structure and metadata context**.

---

## Solution

IDX-Analyst implements **Contextual Retrieval**, inspired by [Anthropic's contextual retrieval approach](https://www.anthropic.com/news/contextual-retrieval), with key innovations:

### 1. **Contextual Text Generation**
Before embedding each chunk, we generate **contextual summaries** using a specialized LLM prompt that includes:
- Company identification and business segment
- Specific financial metrics and reporting periods
- Year-over-year or quarter-over-quarter comparisons
- Market position and strategic context

**Example:**
```
Original Chunk: "Total Assets: 1,234,567 (in millions)...."

Generated Context: "Bank BCA's consolidated balance sheet for FY 2023 
shows total assets of Rp 1,234,567 million, representing a 12% YoY increase 
driven by loan portfolio expansion in the consumer banking segment."

```

### 2. **Hybrid Retrieval with Context Awareness**
- **Dense Retrieval (Qwen 0.6B)**: Captures semantic meaning of contextualized chunks
- **Sparse Retrieval (SPLADE-PP-V2)**: Matches specific financial terms and numbers
- **Context-Aware Reranking (BGE-M3)**: Prioritizes results with matching metadata and relevance

### 3. **Table-Aware Document Processing**
Using **LlamaParse** for intelligent PDF parsing:
- Preserves complex table structures
- Maintains header-row relationships across pages
- Extracts nested tables and multi-level hierarchies
- Handles merged cells and irregular layouts

---

## Goals & Objectives

### Primary Goals
1. **Enable accurate retrieval of financial data from tables** without manual document reading
2. **Maintain context across document sections** to prevent fragmented answers
3. **Support natural language queries** from both technical and non-technical users
4. **Achieve production-grade performance** suitable for real-time applications

### Service Level Objectives (SLOs)

| Metric | Target | Current Performance |
|--------|---------|---------------------|
| Average Response Latency | < 10 seconds | 7s (Cohere), 180s+ (BGE w/ CPU) |
| Hit Rate @ Top-5 | ≥ 80% | 88% (BGE) |

### Success Metrics
- ✅ **96% Hit Rate @ Top-10**: Correct answer appears in top 10 results
- ✅ **69.2% MRR with BGE Rerank**: High ranking precision
- ✅ **Mean rank of 2.21**: Relevant results consistently appear in top 3 positions

---

## RAG Workflow

<figure>
  <img src="static/rag.png" alt="Workflow RAG" width="600" height="620">
  <figcaption>Figure 1: Context-Aware RAG Pipeline</figcaption>
</figure>

### Data Storage Architecture

| Component | Technology | Purpose |
|-----------|------------|---------|
| Vector Store | **Qdrant** | Stores dense + sparse embeddings with 1024-dim vectors |
| Metadata Index | **Qdrant Payload** | Company, tickers, chunk_text, document |
| Document Parser | **LlamaParse** | PDF → structured text/table extraction (separate service) |

---

## 🔍 Contextual Retrieval Innovation

### Context Generation Process

#### Our Specialized Prompt

We use a **domain-specific prompt** designed for Indonesian financial reports:

```python
CONTEXT_GENERATION_PROMPT = """
You are an Investment Manager who specializes in financial analysis, 
specifically for Indonesian stocks. Your job is to provide brief and 
relevant context for the snippets of text from the stock's annual report.

<company_name>
{company_name}
</company_name>

<document>
{document}
</document>

Here is the chunk we want to situate within the whole document:
<chunk>
{chunk}
</chunk>

Provide a concise context (1-3 sentences) considering these guidelines:
1. Identify the company name (MUST), financial metric/topic discussed 
   (revenue, ROE, debt ratio, cash flow, total assets, etc.)
2. Specify the reporting period (Q1/Q2/Q3/Q4 2023, FY 2022, etc.) 
   and any comparisons (YoY, QoQ)
3. Note the business segment if applicable (banking, telecommunications, 
   consumer goods, etc.)
4. If relevant, mention how this relates to company's overall performance, 
   strategy, or Indonesian market position
5. Do not use phrases such as "This section discusses" or "This section 
   provides". Instead, state the context directly.

Please give a short succinct context to situate this chunk within the 
overall document for the purposes of improving search retrieval of the 
chunk. Answer only with the succinct context and nothing else.
"""
```

#### Example Context Generation

**Input:**
```
Company: PT Bank Central Asia Tbk (BCA)
Document: Annual Report 2023 - Consolidated Financial Statements
Chunk: "Total liabilities: Rp 987,654 million
        Total equity: Rp 246,912 million"
```

**Generated Context:**
```
"Bank BCA's FY 2023 balance sheet shows total liabilities of Rp 987,654 million 
and equity of Rp 246,912 million, maintaining a debt-to-equity ratio of 4.0x 
consistent with Indonesian banking sector norms."
```

## Evaluation Performance

To rigorously test the system's effectiveness, we created a **manually curated evaluation dataset**

#### Dataset Structure

| Field | Description | Example |
|-------|-------------|---------|
| `id` | Unique document identifier | "222" |
| `question` | Natural language query in Indonesian | "Berapa total aset Bank BCA tahun 2023?" |
| `context` | Expected relevant document chunk | "Laporan Posisi Keuangan Konsolidasian..." |
| `answer` | Reference answer for validation | "Rp 1,234.5 triliun" |\
### Performance Results

<figure>
  <img src="static/hybrid_reranking.png" alt="Evaluation Retrieval 1">
  <figcaption>Figure 1: Performance of BGE</figcaption>
</figure>

<figure>
  <img src="static/hybrid_reranking_cohere.png" alt="Evaluation Retrieval 2">
  <figcaption>Figure 2: Performance of Cohere<</figcaption>
</figure>

#### Hit Rate Comparison

| Metric | BGE Rerank | Cohere Rerank | Improvement |
|--------|------------|---------------|-------------|
| **Hit@3**  | 76.0%      | 60.0%         | BGE +16% |
| **Hit@5**  | 88.0%      | 80.0%         | BGE +8% |
| **Hit@10** | 96.0%      | 96.0%         | Equal |
| **Hit@20** | 96.0%      | 96.0%         | Equal |

**Key Insight:** BGE Rerank excels at placing the correct answer in **early positions (Top-3, Top-5)**, reducing the need for extensive result scanning.

#### Ranking Quality Metrics

| Metric | BGE Rerank | Cohere Rerank | Winner |
|--------|------------|---------------|---------|
| **MRR** (Mean Reciprocal Rank) | 69.2% | 64.8% | BGE (+4.4%) |
| **NDCG@10** | 75.7% | 72.0% | BGE (+3.7%) |
| **Mean Rank Position** | 2.21 | 2.83 | BGE (lower is better) |

**Analysis:**
- BGE achieves **higher precision in ranking**, meaning the most relevant answer appears earlier
- **Mean rank of 2.21** indicates the correct answer typically appears in position 2-3 with BGE
- Both rerankers show strong **MRR-NDCG correlation (r > 0.95)**, validating ranking consistency

> **⚡ Important Note on Latency:**  
> The BGE reranker latency shown (35-48 seconds) reflects **CPU-only inference** in our development/POC environment. This is **not production performance**.
>
> **Production Deployment (GPU-accelerated):**
> - Expected P50: **0.5-1 seconds** (23x improvement)
> - Expected P95: **1-2 seconds**
> - Hardware: NVIDIA A10 or better
---

## Embedding Strategy: MVP vs Production

### **MVP Phase (Current)** 🚀
**Goal:** Rapid development & model flexibility

- **Embedding API:** [Unified Embedding API](https://github.com/fahmiaziz98/unified-embedding-api)
  - **Rationale:** 
    - Fast development iteration
    - Easy model switching for accuracy testing
    - Lower infrastructure cost during validation
    - Flexible experimentation with different embedding models
  - **Deployment:** Lightweight server (CPU-based is sufficient)
  
- **Reranker:** Cohere API
  - **Rationale:**
    - Production-ready out-of-the-box
    - No GPU infrastructure needed initially
    - Easy integration for proof-of-concept
    - Pay-as-you-go pricing suitable for MVP
  
- **Benefits:**
  - ✅ Lower initial infrastructure cost
  - ✅ Easy testing of different models
  - ✅ Focus on product validation over infrastructure

---

### **Production Phase (Planned)** 🏭
**Goal:** Performance, cost optimization, full control

- **Embedding Server:** Self-hosted on GPU (A10 or higher)
  - **Models to Deploy:**
    - Qwen/Qwen3-Embedding-0.6B
    - prithivida/Splade_PP_en_v2
    - BAAI/bge-reranker-v2-m3
  - **Infrastructure:**
    - GPU: NVIDIA A10 (24GB VRAM) or A100
    - Batch processing for efficiency
    - Model caching & optimization (Text-Inference-Embedding from HuggingFace)
  - **Rationale:** 
    - Cost savings at scale
    - Lower latency
    - Full control over model updates

- **Benefits:**
  - ✅ Lower cost per query at scale
  - ✅ Better latency (no API roundtrip)
  - ✅ Data privacy (all processing in-house)
  - ✅ Custom model fine-tuning capability

---

## Tech Stack

### Core Technologies

| Component | Technology | Version | Purpose |
|-----------|------------|---------|---------|
| **Backend** | FastAPI | 0.109+ | REST API & async operations |
| **Orchestration** | LangGraph | 0.2+ | RAG workflow & agent routing |
| **Vector DB** | Qdrant | 1.7+ | Hybrid dense + sparse storage |
| **PDF Parser** | LlamaParse | Latest | Structure-aware PDF extraction |
| **Dense Encoder** | Qwen 0.6B | Latest | Semantic embeddings (768-dim) |
| **Sparse Encoder** | SPLADE-PP-V2 | Latest | Lexical expansion & term weighting |
| **Reranker** | BGE-M3 | Latest | Cross-encoder contextual ranking |
| **LLM** | GPT-OSS20B + Gemini 2.0 flash | Latest | Context generation & answer synthesis |
| **Containerization** | Docker + Compose | 24+ | Multi-service orchestration |

### Model Details & Links

#### Embedding Models
- **[Qwen/Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)**
  - 0.6B parameters, optimized for multilingual financial text
  - Context window: 8192 tokens
  - Output dimension: 1024
  - Inference speed: ~50ms/sequence (GPU)
  
- **[prithivida/Splade_PP_en_v2](https://huggingface.co/prithivida/Splade_PP_en_v2)**
  - SPLADE++ architecture for sparse retrieval
  - Vocabulary size: 30,522 (BERT tokenizer)
  - Effective on exact-match financial terminology
  - Works well with Indonesian business terms

#### Reranking Models
- **[BAAI/bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3)** ⭐ **Production Choice**
  - Cross-encoder architecture (568M parameters)
  - Multilingual support
  - Inference: 45ms/pair (GPU)
  
- **[Cohere V3 English Reranker](https://docs.cohere.com/v2/docs/rerank)**
  - Production-grade API service
  - Optimized for low-latency inference (API)

#### LLM Models
- **GPT-OSS 20B + Gemini 2.0 Flash**: Context generation & answer synthesis

#### Document Processing
- **[LlamaParse](https://github.com/run-llama/llama_parse)**: 
  - Advanced PDF parsing with table structure preservation
  - Handles complex layouts, merged cells, nested tables
  - API-based service (separate from main pipeline)

---

## Getting Started

### Prerequisites
- Docker 24+ and Docker Compose v2
- Python 3.10+ (for local development)
- **API Keys Required:**
  - Groq (for GPT-OSS 20B)
  - Gemini (for Gemini 2.0 Flash)
  - LlamaParse API key (for PDF parsing)
  - Cohere API key (optional, for Cohere reranker)

### Parse Document using CLI
```bash
python src/document_processor/cli.py \
  --input data/ADRO.pdf \
  --ticker ADRO \
  --company "PT Adaro Energy" \
  --output data/processed \              # Directory (default)
  --output-filename ALL_DATA.json \      # Filename (default)
  --start-page 45 \                       # Optional
  --end-page 50 \                         # Optional
  --mode append                           # append (default) or new
```

### Local Development Setup 

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up environment variables
cp .env.example .env

# 5. Run the API server
make run
```
### Service URLs
- **API Docs (Swagger)**: http://localhost:7860/docs
- **API Docs (ReDoc)**: http://localhost:7860/redoc

---

## Contributing

We welcome contributions from the community! 

### Contribution Guidelines

1. **Fork the repository** and create a feature branch
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** with clear commit messages
   ```bash
   git commit -m "feat: add financial ratio calculation module"
   ```

4. **Update documentation** if needed

5. **Submit a Pull Request** with:
   - Clear description of changes
   - Test results and performance benchmarks
   - Screenshots/demos if applicable

---

## References & Inspiration

This project builds upon cutting-edge research and industry best practices:

### Research Papers
**[Contextual Retrieval (Anthropic, 2024)](https://www.anthropic.com/news/contextual-retrieval)**
- Core inspiration for context generation approach
- Demonstrates 67% reduction in retrieval failures

### Tools & Frameworks
- **[LangChain Documentation](https://python.langchain.com/)** - RAG patterns and best practices
- **[Qdrant Vector Database](https://qdrant.tech/documentation/)** - Hybrid search implementation
- **[LlamaParse](https://github.com/run-llama/llama_parse)** - Advanced PDF parsing
- **[FastAPI Best Practices](https://fastapi.tiangolo.com/)** - Production API design
---

### Getting Help

- **Issues**: [GitHub Issues](https://github.com/fahmiaziz98/idx-analyst/issues)
- **Discussions**: [GitHub Discussions](https://github.com/fahmiaziz98/idx-analyst/discussions)
---

## License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contact & Support

- **Project Maintainer**: Fahmi Aziz Fadhil 
- **Email**: [fahmiazizfadhil09@gmail.com](fahmiazizfadhil09@gmail.com)  
- **LinkedIn**: [Fahmi Aziz Fadhil](https://www.linkedin.com/in/fahmi-aziz-fadhil-979480235/)  
- **GitHub**: [@fahmiaziz98](https://github.com/fahmiaziz98)

---