# OpenCompany — AWS Deployment Guide

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  Internet                                                    │
│      │                                                       │
│      ▼                                                       │
│  API Gateway HTTP API  (or ALB, opt-in)                      │
│      │                                                       │
│      ▼  VPC Link                                             │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  VPC (2 AZs, no NAT)                                   │  │
│  │                                                         │  │
│  │  ┌─────────────────────────────────────┐               │  │
│  │  │  ECS Fargate (public subnet)        │               │  │
│  │  │  ┌─────────┐  ┌──────────────────┐  │               │  │
│  │  │  │  Redis   │  │  OpenCompany App │  │               │  │
│  │  │  │  sidecar │  │  (uvicorn:8000)  │  │               │  │
│  │  │  └─────────┘  └───────┬──────────┘  │               │  │
│  │  └───────────────────────┼─────────────┘               │  │
│  │                          │                              │  │
│  │  ┌───────────────────────▼─────────────┐               │  │
│  │  │  RDS PostgreSQL t4g.micro           │               │  │
│  │  │  (isolated subnet)                  │               │  │
│  │  └─────────────────────────────────────┘               │  │
│  │                                                         │  │
│  │  VPC Endpoints: Secrets Manager, (Bedrock if enabled)   │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                               │
│  AWS Bedrock  ←── IAM role (no API key needed)               │
└─────────────────────────────────────────────────────────────┘
```

## Infrastructure (CDK)

The `infra/` directory contains an AWS CDK (TypeScript) stack that deploys everything.

### Prerequisites

- AWS CLI configured with credentials
- Node.js 18+
- Docker (for building the app image)

### Setup

```bash
cd infra
npm install
npx cdk bootstrap   # first time only, per account/region
```

### Deploy

```bash
# Default: API Gateway + external LLM provider (~$28/mo)
npx cdk deploy

# With ALB instead of API Gateway (~$43/mo)
npx cdk deploy -c use_alb=true

# With Bedrock (Claude) — no API key needed
npx cdk deploy -c model_provider=bedrock-anthropic

# With Bedrock (Nova)
npx cdk deploy -c model_provider=bedrock-nova
```

### Destroy

```bash
npx cdk destroy
```

## Model Provider Options

| Provider | Context flag | Model ID | Auth |
|----------|-------------|----------|------|
| External (default) | `model_provider=external` | Set via Secrets Manager | API key in secrets |
| Bedrock Claude | `model_provider=bedrock-anthropic` | `bedrock/anthropic.claude-sonnet-4-20250514-v1:0` | IAM role (automatic) |
| Bedrock Nova | `model_provider=bedrock-nova` | `bedrock/amazon.nova-pro-v1:0` | IAM role (automatic) |

## Bedrock Configuration

When deploying with a Bedrock provider, the stack automatically:

1. **Sets `LITELLM_MODEL_ID`** to the correct Bedrock model path (LiteLLM's `bedrock/` prefix)
2. **Sets `AWS_REGION_NAME`** to the deployment region
3. **Grants IAM permissions** on the ECS task role:
   - `bedrock:InvokeModel`
   - `bedrock:InvokeModelWithResponseStream`
   - Resource: `arn:aws:bedrock:*::foundation-model/*`
4. **Skips API key secrets** — no `OPENAI_API_KEY` or `OPENAI_API_BASE` created

LiteLLM picks up AWS credentials from the ECS task role automatically (via the container credential provider). No manual key management required.

### Bedrock Prerequisites

- The Bedrock model must be **enabled in your AWS account** for the deployment region. Go to the [Bedrock Model Access](https://console.aws.amazon.com/bedrock/home#/modelaccess) page in the AWS console and request access.
- Default region is `eu-west-1` (set in `infra/bin/app.ts`). Override with:
  ```bash
  CDK_DEFAULT_REGION=us-east-1 npx cdk deploy -c model_provider=bedrock-anthropic
  ```

## Ingress Modes

### API Gateway HTTP API (default)

- Uses VPC Link + Cloud Map service discovery
- No idle cost for the gateway itself (pay-per-request)
- Auto-deploy stage
- Catch-all route proxies to Fargate

### ALB (opt-in with `-c use_alb=true`)

- Application Load Balancer in public subnets
- Health check on `/health`
- Higher base cost (~$15/mo more) but useful if you need WebSocket support or custom listeners

## Resource Summary

| Resource | Spec | Est. Cost |
|----------|------|-----------|
| VPC | 2 AZs, public + isolated subnets, no NAT | ~$0 |
| RDS PostgreSQL | t4g.micro, 20GB, single-AZ | ~$14/mo |
| ECS Fargate | 0.25 vCPU / 512MB, 1 task | ~$9/mo |
| API Gateway HTTP API | Pay-per-request | ~$1/mo |
| ALB (opt-in) | Fixed + per-request | ~$16/mo |
| Secrets Manager | 2 secrets | ~$1/mo |
| CloudWatch Logs | App + Redis | ~$1/mo |
| ECR | Docker image storage | ~$1/mo |
| **Total (API GW mode)** | | **~$28/mo** |
| **Total (ALB mode)** | | **~$43/mo** |

Bedrock costs are usage-based on top of infrastructure (per input/output token).

## Secrets Management

After first deploy, update the placeholder secrets via AWS CLI:

```bash
# App secrets (Telegram token, API auth key)
aws secretsmanager put-secret-value \
  --secret-id opencompany/app-config \
  --secret-string '{"TELEGRAM_BOT_TOKEN":"real-token","API_KEY":"your-api-key"}'

# For external providers, also set:
aws secretsmanager put-secret-value \
  --secret-id opencompany/app-config \
  --secret-string '{"TELEGRAM_BOT_TOKEN":"...","API_KEY":"...","OPENAI_API_KEY":"...","OPENAI_API_BASE":"https://api.openai.com","LITELLM_MODEL_ID":"gpt-4"}'
```

The RDS credentials are auto-generated and stored in a separate secret (ARN printed in stack outputs).

## Stack Outputs

After deploy, the stack prints:

| Output | Description |
|--------|-------------|
| `AppUrl` | Public endpoint URL (API GW or ALB) |
| `DbSecretArn` | RDS credentials secret ARN |
| `AppSecretsArn` | App config secret ARN |
| `EcsCluster` | ECS cluster name |

## Networking Notes

- **No NAT Gateway** — saves ~$32/mo. Fargate tasks run in public subnets with `assignPublicIp: true`.
- **VPC Endpoint for Secrets Manager** — allows Fargate to reach Secrets Manager without NAT.
- **Redis as sidecar** — runs inside the same Fargate task (localhost:6379), ephemeral storage. Fine for pub/sub event bus; not for durable data.
- **RDS in isolated subnets** — only reachable from the Fargate security group on port 5432.

## Dockerfile

The app image is built from the project root `Dockerfile`:

- Base: `python:3.13-slim`
- Uses `uv` for dependency management
- Runs as non-root `appuser`
- Health check: `curl -f http://localhost:8000/health`
- Entrypoint: `uvicorn opencompany.main:app --host 0.0.0.0 --port 8000`

The CDK stack builds and pushes this image to ECR automatically during `cdk deploy`.
