---
name: llm-provider-tool
description: Use when checking InternAgent LLM provider abstraction, Gemma4/Ollama transport, provider health, generation reachability, model name, or timeout diagnostics.
---

# LLM Provider Tool

## Tool Contract
Use this skill to inspect the configured `LLMProvider`. The project name may be `claude`, but the real deployment is Gemma4 through Ollama `api/generate`. Never print API keys or raw provider payloads.

## Script Usage
Run inside the API container:
```powershell
docker compose exec api python /app/skills/llm-provider-tool/scripts/check_provider.py --diagnose
```
Inputs: optional `--diagnose`. Without it, the script only returns provider name and model.

## Output Contract
The script emits compact JSON: `provider`, `model`, and optional `diagnostics` with reachability fields. Errors return `ok=false` with a safe error string.

## Answer Synthesis
Separate tag/model-list reachability from generation reachability. If generation fails or times out, say the app may still be up while model generation is unhealthy.

## Validation
```powershell
python skills/llm-provider-tool/scripts/check_provider.py --self-test
python skills/llm-provider-tool/scripts/check_provider.py --help
docker compose exec api python /app/skills/llm-provider-tool/scripts/check_provider.py
```
