# LLM Risk Boundaries

Qingcheng AI is not claiming production-grade security. The goal is to make the current Agent/RAG system controlled, explainable, and testable enough for internship interview depth.

## Reference Model

This project uses the following public risk and observability references:

- [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [OWASP Top 10 for LLM Applications](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)

## Implemented Boundaries

| Area | Current control |
| --- | --- |
| Prompt injection in RAG | Retrieved chunks are marked as untrusted reference material, not system instructions. Obvious instruction-overwrite phrases are stripped before prompt injection. |
| Tool execution | Tools are selected by server-side allowlist and service logic. The model cannot directly write to the database or call arbitrary tools. |
| Automatic external apply | Disabled. The system can save jobs, open original links, and let the user mark status manually. |
| Recruitment platform crawling | No login bypass, captcha bypass, slider bypass, or anti-bot evasion. Official/public sources and authorized MCP only. |
| Context isolation | AI assistant and interview assistant use separate short-term histories and separate `assistant_memories.assistant_type` scopes. |
| Trace privacy | Metadata stores IDs, summaries, counts, and status. It does not store full prompts, full resume text, secrets, or hidden reasoning chains. |
| RAG source transparency | AI assistant metadata records `retrieval_summary` and lightweight references; Qdrant point IDs are not exposed to users. |
| Fallback transparency | Provider/model failures return fallback notices instead of pretending the model succeeded. |

## Lightweight Trace Fields

SSE `end.metadata` can include:

```json
{
  "request_id": "req-...",
  "agent_run_id": "chat-...",
  "eval_tags": ["ai_assistant", "job_search", "resume_profile", "job_search"],
  "tool_calls_summary": [],
  "retrieval_summary": {},
  "evidence_summary": {},
  "safety_boundary": {
    "tool_allowlist_enforced": true,
    "no_auto_apply": true,
    "no_external_platform_bypass": true,
    "context_isolated": true,
    "raw_prompt_hidden": true
  }
}
```

These fields are intentionally close to GenAI observability concepts without pulling in a full OpenTelemetry SDK yet.

## Not Yet Production-Grade

- No full OpenTelemetry collector, metrics backend, or alerting pipeline.
- No virus scanning for uploaded resumes.
- No long-term audit log retention policy.
- No automated deletion cascade for all derived vectors and memories after user deletion.
- No browser-based authenticated crawling for job platforms.
- No external platform auto-submit.

## Regression Tests To Keep

- Malicious resume/JD/knowledge chunk cannot override tool allowlist.
- AI assistant cannot read interview assistant memories.
- Interview assistant cannot read AI assistant memories.
- RAG answers mark context as reference material and do not expose internal point IDs.
- Job/application tools do not claim an external application was submitted automatically.

