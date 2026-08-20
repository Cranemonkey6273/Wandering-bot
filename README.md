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

Wandering Agent uses the OpenAI API. Customers do not need their own OpenAI/ChatGPT/Codex subscription: the dashboard's owner configures the single server-side OpenAI API key, while credits, permissions, memory, audit trail, and worker controls stay in Wandering Bot.

Set these Railway variables for the live AI agent:

```env
WANDERING_AI_AGENT_PROVIDER=openai
WANDERING_AI_AGENT_MODEL=gpt-4.1-mini
WANDERING_AI_AGENT_API_KEY=your-openai-api-key
WANDERING_AI_AGENT_LLM_TIMEOUT_SECONDS=120
WANDERING_AI_AGENT_LLM_MAX_TOKENS=8000
```

Do not put the API key in the dashboard, GitHub, Discord, browser code, or a customer-facing setting. It belongs only in Railway's encrypted service variables.

## Stripe plan payments and automatic dashboard activation

The public plan buttons use Stripe Payment Links. A customer opening a link is **not** a payment; Wandering Bot only grants access from a Stripe-signed webhook after its `payment_status` is `paid`.

1. In **Owner Console → Billing**, add each paid plan's public Stripe URL and its matching `plink_...` Payment Link ID.
2. In Stripe, add the webhook endpoint `https://YOUR-DOMAIN/api/stripe/billing-webhook` and listen for `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `customer.subscription.updated`, and `customer.subscription.deleted`.
3. Set this Railway variable from that endpoint's Stripe signing secret:

```env
WANDERING_STRIPE_BILLING_WEBHOOK_SECRET=whsec_...
```

4. In each Payment Link's **After payment** settings, select redirect and use:

```text
https://YOUR-DOMAIN/purchase/complete?session_id={CHECKOUT_SESSION_ID}
```

Signed-in dashboard customers are activated immediately after Stripe confirms payment. New customers are returned to the setup page, invite the bot, run `/setup`, then sign into the new dashboard in the same browser; their paid plan is claimed automatically. Never give a Stripe secret key to the dashboard or put it in a public link.

An explicitly configured custom endpoint remains available only if you deliberately choose it, for example for a private model gateway:

```env
WANDERING_AI_AGENT_PROVIDER=custom
WANDERING_AI_AGENT_BASE_URL=https://your-model-server.example.com/v1
WANDERING_AI_AGENT_MODEL=qwen2.5-coder:14b
WANDERING_AI_AGENT_API_KEY=optional-private-gateway-key
WANDERING_AI_AGENT_LLM_TIMEOUT_SECONDS=120
WANDERING_AI_AGENT_LLM_MAX_TOKENS=8000
```

If no model backend is configured, the page still uses the built-in local planner and approval-gated sandbox workflow, but replies will be less intelligent.

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

### Supabase state persistence for ADM rate-limit and dedupe memory

For production reliability, the bot can keep key runtime state in Supabase so deploys/restarts don't wipe ADM scan context.

Set these Railway variables:

```env
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service-role-token>
WANDERING_SUPABASE_STATE_TABLE=bot_state_store
WANDERING_SUPABASE_STATE_FLUSH_SECONDS=20
```

Then run the SQL migration in `supabase/migrations/20260819_add_bot_state_store.sql` (or paste it into the Supabase SQL Editor):

```sql
-- creates:
-- public.bot_state_store(state_key, state_value jsonb, updated_at timestamptz)
```

If you keep using the anonymous key, set `SUPABASE_KEY` instead of
`SUPABASE_SERVICE_ROLE_KEY` and ensure row-level access still allows your bot role.

### Central ADM event-pipeline foundation

For a larger customer base, apply `supabase/migrations/20260820_add_adm_event_pipeline.sql`
after the state-store migration. It creates the durable source scheduler, parsed
event store, online-player snapshots, and Discord delivery outbox used by the
future central ADM collector. The migration intentionally stores only a Nitrado
token fingerprint: customer Nitrado and FTP credentials must remain in encrypted
worker configuration or deployment secrets, never in Supabase event rows.
