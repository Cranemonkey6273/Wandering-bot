# Wandering-bot

## AI Development Agent sandbox setup

The dashboard is the control plane. Keep Railway safe and run command execution on a separate VPS or local machine with Docker installed.

### Railway dashboard variables

Set these on the Railway service that runs `python bot.py`:

```env
WANDERING_AI_AGENT_DOCKER_ENABLED=false
WANDERING_AI_AGENT_WORKER_URL=https://your-worker-domain.example.com
WANDERING_AI_AGENT_WORKER_TOKEN=use-a-long-random-secret
WANDERING_AI_AGENT_COMMAND_TIMEOUT_SECONDS=900
```

Leave `WANDERING_AI_AGENT_WORKER_URL` blank if you only want planning, approvals, and audit logs.

### AI model backend

Wandering Agent does not require every customer to have an OpenAI/ChatGPT/Codex subscription. The dashboard is the control plane, credits, permissions, memory, audit trail, and worker system. The model backend is swappable.

For your own hosted model, run an OpenAI-compatible server with Ollama, vLLM, LM Studio, or another private model gateway, then set Railway like this:

```env
WANDERING_AI_AGENT_PROVIDER=custom
WANDERING_AI_AGENT_BASE_URL=https://your-model-server.example.com/v1
WANDERING_AI_AGENT_MODEL=qwen2.5-coder:14b
WANDERING_AI_AGENT_API_KEY=optional-private-gateway-key
WANDERING_AI_AGENT_LLM_TIMEOUT_SECONDS=45
```

If no model backend is configured, the page still uses the built-in local planner and approval-gated sandbox workflow, but replies will be less intelligent.

If you explicitly want to use an OpenAI-compatible hosted provider instead:

```env
WANDERING_AI_AGENT_PROVIDER=openai
WANDERING_AI_AGENT_MODEL=gpt-4.1-mini
WANDERING_AI_AGENT_API_KEY=your-provider-key
```

### Worker machine variables

Run `ai_sandbox_worker.py` on the separate Docker machine with the same token:

```env
WANDERING_AI_WORKER_TOKEN=use-a-long-random-secret
WANDERING_AI_WORKER_ROOT=/srv/wandering-ai-workspaces
WANDERING_AI_WORKER_DOCKER_IMAGE=python:3.12-slim
WANDERING_AI_WORKER_TIMEOUT_SECONDS=900
PORT=8787
```

Start the worker:

```bash
python ai_sandbox_worker.py
```

The dashboard calls:

- `GET /health`
- `GET /api/agent/jobs`
- `POST /api/agent/jobs`
- `GET /api/agent/jobs/<job_id>`
- `POST /api/agent/jobs/<job_id>/cancel`

Only the Primary Owner can approve, run, sync, or cancel worker jobs.

### Failsafe behavior

- If Railway restarts after dispatching a job, the worker keeps running and stores job results in `WANDERING_AI_WORKER_JOBS_FILE`.
- When Railway comes back, use **Recover / Sync Worker Jobs** on the AI Development Agent page to import forgotten worker jobs.
- If the worker itself restarts while a job is running, that job is marked `interrupted` so it will not sit forever as running. Re-run it from the dashboard if needed.
- Agent conversations create durable runs. Pick a run in the chat composer or press **Continue Run** to attach the next message, task, approval, and sandbox job to the same work thread after refreshes or Railway restarts.
