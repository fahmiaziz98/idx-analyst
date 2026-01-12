import modal

# Configuration
MODEL_ID = "unsloth/Qwen3-VL-8B-Instruct-bnb-4bit"
MODEL_NAME = "Qwen3-VL"
REVISION = "main"
GPU_TYPE = "A100"
MINUTES = 60
VLLM_PORT = 8000

# Docker image
vllm_image = (
    modal.Image.from_registry("nvidia/cuda:12.8.0-devel-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    .uv_pip_install(
        "vllm==0.13.0",
        "huggingface-hub==0.36.0",
        "bitsandbytes>=0.46.1"
    )
    .env({"HF_XET_HIGH_PERFORMANCE": "1"}) 
)

# Persistent volumes for model caching
hf_cache_vol = modal.Volume.from_name("hf-cache-qwen3-vl", create_if_missing=True)
vllm_cache_vol = modal.Volume.from_name("vllm-cache-qwen3-vl", create_if_missing=True)

app = modal.App("qwen3vl-8b-4bit-vllm-server")

@app.function(
    image=vllm_image,
    gpu=GPU_TYPE,
    scaledown_window=5 * MINUTES,
    timeout=20 * MINUTES,
    volumes={
        "/root/.cache/huggingface": hf_cache_vol,
        "/root/.cache/vllm": vllm_cache_vol,
    },
)
@modal.web_server(port=VLLM_PORT, startup_timeout=10 * MINUTES)
def serve():
    import subprocess
    import time

    cmd = [
        "python", "-m", "vllm.entrypoints.openai.api_server",
        "--model", MODEL_ID,
        "--served-model-name", MODEL_NAME,
        "--host", "0.0.0.0",
        "--port", str(VLLM_PORT),
        "--quantization", "bitsandbytes",  # Unsloth bnb
        "--load-format", "bitsandbytes",   
        "--max-model-len", "32768",
        "--disable-log-requests",         
        "--trust-remote-code",             
        "--enforce-eager",                 
    ]

    process = subprocess.Popen(cmd)
    return process