/**
 * OpenCompany AWS CDK stack.
 *
 * Deploys: VPC | RDS Postgres | ECS Fargate (app + Redis sidecar) | ALB.
 *
 * Usage:
 *   cd infra && npm install
 *   npx cdk bootstrap                              # first time only
 *   npx cdk deploy -c model_provider=bedrock-anthropic
 *   npx cdk deploy -c model_provider=external      # LiteLLM / OpenAI proxy
 */

import * as cdk from "aws-cdk-lib";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as ecs from "aws-cdk-lib/aws-ecs";
import * as ecr_assets from "aws-cdk-lib/aws-ecr-assets";
import * as iam from "aws-cdk-lib/aws-iam";
import * as logs from "aws-cdk-lib/aws-logs";
import * as rds from "aws-cdk-lib/aws-rds";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import * as elbv2 from "aws-cdk-lib/aws-elasticloadbalancingv2";
import { Construct } from "constructs";
import * as path from "path";

/** Supported model providers. Bedrock options use IAM auth (no API key needed). */
type ModelProvider = "bedrock-anthropic" | "bedrock-nova" | "external";

const BEDROCK_MODELS: Record<string, string> = {
  "bedrock-anthropic": "us.anthropic.claude-sonnet-4-20250514-v1:0",
  "bedrock-nova": "amazon.nova-pro-v1:0",
};

export interface OpenCompanyStackProps extends cdk.StackProps {
  modelProvider?: ModelProvider;
}

export class OpenCompanyStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: OpenCompanyStackProps) {
    super(scope, id, props);

    const modelProvider: ModelProvider = props.modelProvider ?? "external";
    const isBedrock = modelProvider.startsWith("bedrock");

    // ── VPC ─────────────────────────────────────────────────────────────
    // 2 AZs, public + isolated subnets. No NAT gateway (Fargate in public
    // subnets; RDS in isolated subnets reachable via SG only).
    const vpc = new ec2.Vpc(this, "Vpc", {
      maxAzs: 2,
      natGateways: 0,
      subnetConfiguration: [
        { name: "Public", subnetType: ec2.SubnetType.PUBLIC, cidrMask: 24 },
        { name: "Isolated", subnetType: ec2.SubnetType.PRIVATE_ISOLATED, cidrMask: 24 },
      ],
    });

    // Interface endpoints so isolated/public subnets can reach AWS services
    // without a NAT gateway.
    vpc.addInterfaceEndpoint("SecretsManagerEndpoint", {
      service: ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
    });
    if (isBedrock) {
      vpc.addInterfaceEndpoint("BedrockRuntimeEndpoint", {
        service: new ec2.InterfaceVpcEndpointService(
          `com.amazonaws.${this.region}.bedrock-runtime`
        ),
      });
    }

    // ── RDS PostgreSQL t4g.micro ─────────────────────────────────────────
    const dbSg = new ec2.SecurityGroup(this, "DbSg", { vpc, description: "RDS Postgres" });
    const db = new rds.DatabaseInstance(this, "Postgres", {
      engine: rds.DatabaseInstanceEngine.postgres({
        version: rds.PostgresEngineVersion.VER_17,
      }),
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T4G, ec2.InstanceSize.MICRO),
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      securityGroups: [dbSg],
      databaseName: "opencompany",
      credentials: rds.Credentials.fromGeneratedSecret("opencompany"),
      allocatedStorage: 20,
      maxAllocatedStorage: 100,
      storageEncrypted: true,
      removalPolicy: cdk.RemovalPolicy.SNAPSHOT,
      deletionProtection: false, // set true in production after first successful deploy
      backupRetention: cdk.Duration.days(7),
    });

    // ── App secrets (update after first deploy via AWS console / CLI) ────
    const secretValues: Record<string, string> = {
      TELEGRAM_BOT_TOKEN: "CHANGE_ME",
      API_KEY: "CHANGE_ME",
    };
    if (!isBedrock) {
      secretValues.OPENAI_API_KEY = "CHANGE_ME";
      secretValues.OPENAI_API_BASE = "https://api.openai.com";
      secretValues.LITELLM_MODEL_ID = "gpt-4";
    }
    const appSecret = new secretsmanager.Secret(this, "AppSecret", {
      secretName: "opencompany/app-config",
      generateSecretString: {
        secretStringTemplate: JSON.stringify(secretValues),
        generateStringKey: "_generated",
      },
    });

    // ── Docker image (AMD64 — Fargate requires x86_64) ───────────────────
    const image = new ecr_assets.DockerImageAsset(this, "AppImage", {
      directory: path.join(__dirname, "../.."), // repo root
      platform: ecr_assets.Platform.LINUX_AMD64,
      exclude: [
        "infra", "docs", ".git", ".github", "tests", "workspaces",
        ".venv", ".ruff_cache", ".pytest_cache", "*.egg-info",
      ],
    });

    // ── ECS cluster ──────────────────────────────────────────────────────
    const cluster = new ecs.Cluster(this, "Cluster", { vpc });

    // ── Fargate task definition ──────────────────────────────────────────
    const taskDef = new ecs.FargateTaskDefinition(this, "TaskDef", {
      cpu: 256,
      memoryLimitMiB: 512,
    });

    // Bedrock IAM — covers both foundation-model and cross-region
    // inference-profile ARNs (us.anthropic.* uses inference profiles).
    if (isBedrock) {
      taskDef.addToTaskRolePolicy(
        new iam.PolicyStatement({
          sid: "AllowBedrockInvoke",
          effect: iam.Effect.ALLOW,
          actions: ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
          resources: [
            // Scoped to Anthropic Claude and Amazon Nova models only
            `arn:aws:bedrock:*::foundation-model/anthropic.*`,
            `arn:aws:bedrock:*::foundation-model/amazon.nova*`,
            `arn:aws:bedrock:${this.region}:${this.account}:inference-profile/*`,
          ],
        })
      );
    }

    appSecret.grantRead(taskDef.taskRole);
    db.secret?.grantRead(taskDef.taskRole);

    const logGroup = new logs.LogGroup(this, "AppLogs", {
      logGroupName: "/aws/ecs/opencompany",
      retention: logs.RetentionDays.THREE_MONTHS,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // ── Environment variables ────────────────────────────────────────────
    const environment: Record<string, string> = {
      LOG_LEVEL: "INFO",
      REDIS_URL: "redis://localhost:6379/0",
    };
    if (isBedrock) {
      environment.MODEL_PROVIDER = "bedrock";
      environment.BEDROCK_MODEL_ID = BEDROCK_MODELS[modelProvider] ?? "";
      environment.AWS_REGION = this.region;
    } else {
      environment.MODEL_PROVIDER = "litellm";
    }

    // ── App container ────────────────────────────────────────────────────
    const appContainer = taskDef.addContainer("app", {
      image: ecs.ContainerImage.fromDockerImageAsset(image),
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: "app", logGroup }),
      environment,
      secrets: {
        TELEGRAM_BOT_TOKEN: ecs.Secret.fromSecretsManager(appSecret, "TELEGRAM_BOT_TOKEN"),
        API_KEY: ecs.Secret.fromSecretsManager(appSecret, "API_KEY"),
        ...(isBedrock
          ? {}
          : {
              OPENAI_API_KEY: ecs.Secret.fromSecretsManager(appSecret, "OPENAI_API_KEY"),
              OPENAI_API_BASE: ecs.Secret.fromSecretsManager(appSecret, "OPENAI_API_BASE"),
              LITELLM_MODEL_ID: ecs.Secret.fromSecretsManager(appSecret, "LITELLM_MODEL_ID"),
            }),
      },
      // Health check mirrors Dockerfile HEALTHCHECK.
      // start-period=120s covers slow cold-start (DB migrations + persona seeding).
      healthCheck: {
        command: ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
        startPeriod: cdk.Duration.seconds(120),
        retries: 3,
      },
      portMappings: [{ containerPort: 8000 }],
    });

    if (db.secret) {
      appContainer.addSecret("DB_HOST", ecs.Secret.fromSecretsManager(db.secret, "host"));
      appContainer.addSecret("DB_PORT", ecs.Secret.fromSecretsManager(db.secret, "port"));
      appContainer.addSecret("DB_USER", ecs.Secret.fromSecretsManager(db.secret, "username"));
      appContainer.addSecret("DB_PASSWORD", ecs.Secret.fromSecretsManager(db.secret, "password"));
      appContainer.addEnvironment("DB_NAME", "opencompany");
    }

    // ── Redis sidecar (ephemeral — pub/sub event bus only) ───────────────
    taskDef.addContainer("redis", {
      image: ecs.ContainerImage.fromRegistry("redis:7-alpine"),
      memoryLimitMiB: 128,
      essential: false,
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: "redis", logGroup }),
      portMappings: [{ containerPort: 6379 }],
    });

    // ── Security groups ──────────────────────────────────────────────────
    const ecsSg = new ec2.SecurityGroup(this, "EcsSg", { vpc, description: "Fargate app" });
    const albSg = new ec2.SecurityGroup(this, "AlbSg", { vpc, description: "ALB" });

    albSg.addIngressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(80), "HTTP from internet");
    ecsSg.addIngressRule(albSg, ec2.Port.tcp(8000), "ALB to ECS");
    dbSg.addIngressRule(ecsSg, ec2.Port.tcp(5432), "ECS to RDS");

    // ── Fargate service ──────────────────────────────────────────────────
    const service = new ecs.FargateService(this, "Service", {
      cluster,
      taskDefinition: taskDef,
      desiredCount: 1,
      assignPublicIp: true,
      vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC },
      securityGroups: [ecsSg],
      enableExecuteCommand: false,
      minHealthyPercent: 100,
      maxHealthyPercent: 200,
      // Allow 3 min for DB migrations + persona seeding before ALB health checks count.
      healthCheckGracePeriod: cdk.Duration.seconds(180),
    });

    // ── Application Load Balancer ────────────────────────────────────────
    // CORS_ORIGINS is set to the ALB DNS after creation so the app restricts
    // cross-origin requests to itself only.
    const alb = new elbv2.ApplicationLoadBalancer(this, "Alb", {
      vpc,
      internetFacing: true,
      securityGroup: albSg,
      vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC },
    });

    const listener = alb.addListener("Http", {
      port: 80,
      open: false, // security group controls access
    });

    listener.addTargets("EcsTarget", {
      port: 8000,
      protocol: elbv2.ApplicationProtocol.HTTP,
      targets: [service],
      healthCheck: {
        path: "/health",
        interval: cdk.Duration.seconds(30),
        healthyThresholdCount: 2,
        unhealthyThresholdCount: 3,
      },
      deregistrationDelay: cdk.Duration.seconds(30),
    });

    // Restrict CORS to the ALB origin so the API rejects cross-site requests.
    appContainer.addEnvironment("CORS_ORIGINS", `http://${alb.loadBalancerDnsName}`);

    // ── Outputs ──────────────────────────────────────────────────────────
    new cdk.CfnOutput(this, "AppUrl", {
      description: "Application Load Balancer DNS name",
      value: `http://${alb.loadBalancerDnsName}`,
    });
    new cdk.CfnOutput(this, "EcsCluster", { value: cluster.clusterName });
    new cdk.CfnOutput(this, "ModelProvider", { value: modelProvider });
    new cdk.CfnOutput(this, "SecretArn", { value: appSecret.secretArn });
    new cdk.CfnOutput(this, "DbSecretArn", { value: db.secret!.secretArn });
  }
}
