# OpenCompany — AWS CDK Deployment

Deploys OpenCompany to AWS using ECS Fargate with a Redis sidecar, RDS PostgreSQL, and configurable ingress (API Gateway HTTP API or ALB).

## Model provider configuration

The application supports two model backends:

| Provider | How it works | Auth |
|----------|-------------|------|
| **Bedrock** (default) | Direct AWS Bedrock API via `strands.models.BedrockModel` | IAM role — no API keys needed |
| **LiteLLM** | Proxy-based via `strands.models.litellm.LiteLLMModel` | API key + base URL |

### Resolution order

1. `model_provider` in `config/company.yaml` (values: `bedrock` or `litellm`)
2. `MODEL_PROVIDER` environment variable
3. Default: `bedrock`

### Bedrock IAM policy

When using Bedrock, the ECS task role gets this policy automatically:

```json
{
  "Effect": "Allow",
  "Action": [
    "bedrock:InvokeModel",
    "bedrock:InvokeModelWithResponseStream"
  ],
  "Resource": "arn:aws:bedrock:<region>::foundation-model/<model-id>"
}
```

A VPC endpoint for `bedrock-runtime` is also created to keep traffic on the AWS backbone and avoid NAT costs.

## Prerequisites

### Tools

| Tool | Version | Install |
|------|---------|---------|
| Node.js | >= 18 | `brew install node` |
| AWS CLI | >= 2.x | `brew install awscli` |
| AWS CDK | >= 2.180 | installed via `npm install` (local) |
| Docker | running | `brew install --cask docker` |

### AWS account setup

1. **Configure AWS CLI** with credentials that have admin access (or at least IAM, VPC, ECS, RDS, ECR, Secrets Manager, CloudFormation, API Gateway permissions):

   ```bash
   aws configure
   # or use SSO:
   aws configure sso
   ```

2. **Bedrock model access** (only if using `bedrock-anthropic` or `bedrock-nova`):

   Bedrock foundation models must be explicitly enabled per region. Go to the [AWS Bedrock console](https://console.aws.amazon.com/bedrock/home#/modelaccess) → **Model access** → **Manage model access** and enable:

   - **Anthropic Claude Sonnet 4** — for `bedrock-anthropic`
   - **Amazon Nova Pro** — for `bedrock-nova`

   This may take a few minutes to activate. No cost until you actually invoke the model.

## Deploy

```bash
cd infra
npm install
```

### Bootstrap CDK (first time per account/region)

```bash
npx cdk bootstrap
```

### Choose your model provider

| Command | Provider | Auth | Notes |
|---------|----------|------|-------|
| `npx cdk deploy -c model_provider=bedrock-anthropic` | Claude via Bedrock | IAM (automatic) | No API key needed |
| `npx cdk deploy -c model_provider=bedrock-nova` | Nova Pro via Bedrock | IAM (automatic) | No API key needed |
| `npx cdk deploy` | External (OpenAI, LiteLLM proxy, etc.) | API key | Set key in Secrets Manager after deploy |

### Choose your ingress

| Flag | Ingress | Est. cost |
|------|---------|-----------|
| *(default)* | API Gateway HTTP API + VPC Link | ~$1/mo |
| `-c use_alb=true` | Application Load Balancer | ~$16/mo |

### Example: full deploy command

```bash
# Bedrock Anthropic + API Gateway (cheapest, ~$28/mo infra)
npx cdk deploy -c model_provider=bedrock-anthropic

# Bedrock Nova Pro + ALB (~$43/mo infra)
npx cdk deploy -c model_provider=bedrock-nova -c use_alb=true

# External provider + API Gateway (~$28/mo infra + LLM costs)
npx cdk deploy
```

## Post-deploy configuration

### 1. Update app secrets

After the first deploy, the stack creates a Secrets Manager secret with placeholder values. Update it with real values:

**For Bedrock providers** (only Telegram + API key needed):

```bash
aws secretsmanager put-secret-value \
  --secret-id opencompany/app-config \
  --secret-string '{
    "TELEGRAM_BOT_TOKEN": "your-telegram-token",
    "API_KEY": "your-api-auth-key"
  }'
```

**For external providers** (also need LLM credentials):

```bash
aws secretsmanager put-secret-value \
  --secret-id opencompany/app-config \
  --secret-string '{
    "OPENAI_API_KEY": "sk-...",
    "OPENAI_API_BASE": "https://api.openai.com",
    "LITELLM_MODEL_ID": "gpt-4",
    "TELEGRAM_BOT_TOKEN": "your-telegram-token",
    "API_KEY": "your-api-auth-key"
  }'
```

### 2. Force ECS to pick up new secrets

After updating secrets, restart the ECS service to pick up the new values:

```bash
aws ecs update-service \
  --cluster $(aws cloudformation describe-stacks --stack-name OpenCompanyStack \
    --query 'Stacks[0].Outputs[?OutputKey==`EcsCluster`].OutputValue' --output text) \
  --service $(aws ecs list-services \
    --cluster $(aws cloudformation describe-stacks --stack-name OpenCompanyStack \
      --query 'Stacks[0].Outputs[?OutputKey==`EcsCluster`].OutputValue' --output text) \
    --query 'serviceArns[0]' --output text) \
  --force-new-deployment
```

### 3. Get the app URL

```bash
aws cloudformation describe-stacks --stack-name OpenCompanyStack \
  --query 'Stacks[0].Outputs[?OutputKey==`AppUrl`].OutputValue' --output text
```

## Architecture

```
                            ┌─────────────────────────────────────────┐
Internet ──► API GW / ALB ──►  ECS Fargate (public subnet)           │
                            │  ┌──────────┐  ┌──────────────────┐    │
                            │  │ Redis 7   │  │ OpenCompany app  │    │
                            │  │ (sidecar) │◄─│ (FastAPI :8000)  │    │
                            │  └──────────┘  └────────┬─────────┘    │
                            └─────────────────────────┼──────────────┘
                                                      │
                            ┌─────────────────────────▼──────────────┐
                            │  RDS PostgreSQL t4g.micro               │
                            │  (isolated subnet)                      │
                            └─────────────────────────────────────────┘
                                                      │
                            ┌─────────────────────────▼──────────────┐
                            │  AWS Bedrock (optional)                 │
                            │  Claude / Nova Pro via IAM              │
                            └─────────────────────────────────────────┘
```

## Estimated monthly costs

| Component | Cost |
|-----------|------|
| ECS Fargate (0.25 vCPU, 512MB) | ~$9 |
| RDS PostgreSQL t4g.micro | ~$14 |
| VPC Endpoint (Secrets Manager) | ~$7 |
| API Gateway HTTP API | ~$1 |
| ALB (if enabled) | ~$16 |
| ECR, CloudWatch Logs | ~$1 |
| **Total (API GW)** | **~$32** |
| **Total (ALB)** | **~$47** |

Bedrock model costs are usage-based and not included above.

## Useful commands

```bash
npx cdk diff                     # preview changes
npx cdk deploy                   # deploy stack
npx cdk destroy                  # tear down (RDS snapshots retained)
npx cdk synth                    # emit CloudFormation template

# View logs
aws logs tail /aws/ecs/opencompany --follow

# SSH into running task (requires ECS Exec enabled)
aws ecs execute-command --cluster <cluster> --task <task-id> \
  --container app --interactive --command /bin/sh
```

## Teardown

```bash
npx cdk destroy
```

RDS will create a final snapshot before deletion (configurable via `removalPolicy` in the stack). To also delete snapshots, do so manually in the AWS console.
