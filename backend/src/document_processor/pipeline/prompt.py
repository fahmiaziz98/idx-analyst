# ============================================================================
# CONTEXTUAL PROMPTS (for LLM contextualization)
# ============================================================================

SYSTEM_PROMPT = """You are an expert financial analyst specializing in Indonesian equity markets.
Your job is to add brief contextual information to financial document chunks to improve search retrieval."""

TABLE_PROMPT = """Generate context to this financial table from an Indonesian annual report.

<full_document>
{document}
</full_document>

<table>
{chunk}
</table>

TASK:
Generate a 4-6 sentence context that identifies:
- Identify the company name (MUST)
- Financial statement type (balance sheet, income statement, cash flow, etc.)
- Reporting period (FY 2024, Q3 2023, etc.)
- Key line items with their values
- Major changes (YoY, QoQ percentages)

CRITICAL RULES:
1. "dalam jutaan Rupiah" = values already ÷ 1,000,000
   - Table shows 4,751,621 = actual value Rp 4.75 trillion
   - Table shows 943,915 = actual value Rp 943.9 billion
   - Table shows 915 = actual value Rp 915 million

2. ALWAYS use this exact format:
   ✓ "Rp 4.75T" (trillion, uppercase T)
   ✓ "Rp 943.9B" (billion, uppercase B)
   ✓ "Rp 53M" (million, uppercase M)
   ✓ "up 16% YoY" or "down 16% YoY"
   ✓ "FY 2024" or "Q1 2024"

   ✘ NEVER use: "tril", "trillion", "t", "T.", "FY-2024"

3. Be specific: "Operating cash Rp 3.68T (2024) vs Rp 4.36T (2023), down 16%".
4. No meta-commentary: describe the table directly.
5. Do not use phrases such as "This section discusses" or "This section provides". Instead, state the context directly.

Answer only with the succinct context and nothing else.
"""


# ============================================================================
# PARSER PROMPTS (for VLM parsing)
# ============================================================================

PARSER_SYSTEM_PROMPT = """You are a specialized AI parser for Indonesian financial documents (Annual Reports, Financial Statements).

Your core mission is **Layout-Aware Optical Character Recognition (OCR) to Markdown**.

**STRICT BEHAVIORAL RULES:**
1. **Accuracy is Paramount:** Financial numbers must be exact. "1.234,56" must stay "1.234,56". Never round or format numbers differently.
2. **Table Specialist:** You typically encounter complex financial tables. Render them as clean Markdown tables.
3. **No Conversational Filler:** NEVER output text like "Here is the table" or "Sure, I can help". Output **ONLY** the raw Markdown content.
4. **Structural Integrity:** Use headers (#, ##) to reflect font size and hierarchy in the visual document.

Here the image: 
"""

PARSER_USER_PROMPT = """<image>

Convert this document page to Markdown format following these requirements:

**Structure:**
- Preserve the original document hierarchy and layout
- Use proper heading levels (# for main titles, ## for sections, etc.)
- Maintain the logical flow of information

**Tables:**
- Convert ALL tables to proper Markdown table format with | separators
- Preserve column alignment and headers
- Include all rows without omission

**Text:**
- Extract ALL text with 100% accuracy - never paraphrase or summarize
- Preserve numerical values, dates, and percentages exactly as shown
- Maintain formatting like bold (**text**) and italic (*text*) where visible

**Lists:**
- Use proper Markdown list syntax (- for bullets, 1. for numbered)
- Preserve nested list indentation

**Output Format:**
- Return ONLY the Markdown content
- No preamble, explanations, or meta-commentary
- No code block wrappers (no ```markdown)
- Start directly with the content"""
# PARSER_USER_PROMPT = """<image>

# Parse this financial document page to Markdown following these rules:

# ## 1. HEADERS & TITLES
# ```markdown
# # Main Title (if present)
# ## Section Title
# ### Subsection
# ```

# ## 2. BILINGUAL LISTS
# When names/items have both Indonesian and English:
# ```markdown
# #### Dewan Komisaris / Board of Commissioners
# **Komisaris Utama** | **President Commissioner**
# - Name 1
# - Name 2

# **Komisaris Independen** | **Independent Commissioners**
# - Name A
# - Name B
# ```

# ## 3. TABLES
# For complex tables, use full Markdown syntax:
# ```markdown
# | Column 1 | Column 2 | Column 3 |
# |----------|----------|----------|
# | Data 1   | Data 2   | Data 3   |
# ```

# **Critical for tables:**
# - Include ALL columns (even narrow ones)
# - Add header separator row (|---|---|)
# - Right-align numbers with `:` in separator (|---:|)
# - Include footnotes below table with * ** markers
# - Preserve percentage symbols (100.00%)

# ## 4. NUMBERS
# Preserve exactly as shown:
# - Thousands separator: 3,887,896 (not 3887896)
# - Percentages: 100.00% (not 100%)
# - Decimals: 99.99% (keep .99)

# Output ONLY the Markdown. No preamble, no explanations."""

