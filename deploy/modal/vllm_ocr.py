"""
Modal Deployment for DeepSeek-OCR vLLM Server
==============================================

Deploy with:
    modal deploy modal_ocr_server.py

Get URL:
    modal app show deepseek-ocr-server
"""

import modal

# Configuration
MODEL_ID = "deepseek-ai/DeepSeek-OCR"
MODEL_NAME = "deepseek-ocr"
REVISION = "main"
GPU_TYPE = "L4"  # Cost-effective: $0.80/hr. Use "A100-40GB" for high throughput
MINUTES = 60
VLLM_PORT = 8000

# Docker image
vllm_image = (
    modal.Image.from_registry("nvidia/cuda:12.8.0-devel-ubuntu22.04", add_python="3.12")
    .dockerfile_commands(
        [
            "RUN mkdir -p /opt/vllm/templates", 
            "COPY ./modal/template/template_deepseek_ocr.jinja /opt/vllm/templates/template_deepseek_ocr.jinja" 
        ]
    )
    .entrypoint([])
    .uv_pip_install(
        "vllm==0.13.0",
        "huggingface-hub==0.36.0",
    )
    .env({"HF_XET_HIGH_PERFORMANCE": "1"})  # faster model transfers
)

# Persistent volumes for model caching
hf_cache_vol = modal.Volume.from_name("hf-cache-deepseek-ocr", create_if_missing=True)
vllm_cache_vol = modal.Volume.from_name("vllm-cache-ocr", create_if_missing=True)

app = modal.App("deepseek-ocr-server")


@app.function(
    image=vllm_image,
    gpu=GPU_TYPE,
    scaledown_window=15 * MINUTES,  # Keep warm for 15 minutes after last request
    timeout=20 * MINUTES,  # Allow up to 20 minutes for initial model loading
    volumes={
        "/root/.cache/huggingface": hf_cache_vol,
        "/root/.cache/vllm": vllm_cache_vol,
    },
)
@modal.concurrent(max_inputs=32)  # Handle up to 32 concurrent requests (batching)
@modal.web_server(port=VLLM_PORT, startup_timeout=20 * MINUTES)
def serve():
    """
    Serve DeepSeek-OCR via vLLM with OpenAI-compatible API
    
    API Endpoint: https://<your-modal-url>/v1/chat/completions
    Model Name: deepseek-ocr
    
    Compatible with OpenAI Python client:
        from openai import OpenAI
        client = OpenAI(
            api_key="EMPTY",
            base_url="https://<your-modal-url>/v1"
        )
    """
    import subprocess
    
    cmd = [
        "vllm", "serve",
        MODEL_ID,
        "--revision", REVISION,
        "--served-model-name", MODEL_NAME,
        "--host", "0.0.0.0",
        "--port", str(VLLM_PORT),
        # "--disable-log-requests",  # Add this instead
        
        # CRITICAL: DeepSeek-OCR specific configuration
        "--logits_processors", 
        "vllm.model_executor.models.deepseek_ocr:NGramPerReqLogitsProcessor",
        "--no-enable-prefix-caching",  # OCR doesn't benefit from prefix caching
        "--mm-processor-cache-gb", "0",  # Disable multimodal cache to save memory
        "--enable-log-requests",
        "--chat-template",
        "/opt/vllm/templates/template_deepseek_ocr.jinja",  # by default ini aku ambil dari github,
        
        # Performance tuning for L4 (24GB VRAM)
        "--max-num-batched-tokens", "16384",
        "--gpu-memory-utilization", "0.95",
        "--max-model-len", "8192",
        
        # # For A100-40GB (40GB VRAM)
        # "--max-num-batched-tokens", "32768",  # 2x from L4
        # "--gpu-memory-utilization", "0.95",   # same
        # "--max-model-len", "16384",           # 2x from L4

        # # For A100-80GB (80GB VRAM)
        # "--max-num-batched-tokens", "65536",  # 4x from L4
        # "--gpu-memory-utilization", "0.95",   # same
        # "--max-model-len", "32768",           # 4x from L4

        # # For H100 (80GB VRAM + faster)
        # "--max-num-batched-tokens", "65536",  # 4x from L4
        # "--gpu-memory-utilization", "0.95",   # same
        # "--max-model-len", "32768",           # 4x from L4

        # Logging
        "--uvicorn-log-level", "info",
    ]
    
    print("=" * 80)
    print("Starting DeepSeek-OCR vLLM Server")
    print("=" * 80)
    print("Command:", " ".join(cmd))
    print("=" * 80)
    
    subprocess.Popen(" ".join(cmd), shell=True)


