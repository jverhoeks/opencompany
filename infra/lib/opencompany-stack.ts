import * as cdk from "aws-cdk-lib";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as ecs from "aws-cdk-lib/aws-ecs";
import * as ecr_assets from "aws-cdk-lib/aws-ecr-assets";
import * as iam from "aws-cdk-lib/aws-iam";
import * as logs from "aws-cdk-lib/aws-logs";
import * as rds from "aws-cdk-lib/aws-rds";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import * as apigwv2 from "aws-cdk-lib/aws-apigatewayv2";
import * as elbv2 from "aws-cdk-lib/aws-elasticloadbalancingv2";
import * as servicediscovery from "aws-cdk-lib/aws-servicediscovery";
import { Construct } from "constructs";

export interface OpenCompanyStackProps extends cdk.StackProps {
  modelProvider: string; // "bedrock-anthropic" | "bedrock-nova" | "external"
  useAlb: boolean;
}

// Bedrock model IDs per provider choice
const BEDROCK_MODELS: Record<string, { modelId: string; envModelId: string }> = {
  "bedrock-anthropic": {
    modelId: "us.anthropic.claude-sonnet-4-20250514-v1:0",
    envModelId: "us.anthropic.claude-sonnet-4-20250514-v1:0",
  },
  "bedrock-nova": {
    modelId: "amazon.nova-pro-v1:0",
    envModelId: "amazon.nova-pro-v1:0",
  },
};

export class OpenCompanyStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: OpenCompanyStackProps) {
    super(scope, id, props);

    const isBedrock = props.modelProvider.startsWith("bedrock");

    // ── VPC ────────────────────────────────────────────────────────────
    const vpc = new ec2.Vpc(this, "Vpc", {
      maxAzs: 2,
      natGateways: 0, // keep costs low — Fargate in public subnet
      subnetConfiguration: [
        { name: "Public", subnetType: ec2.SubnetType.PUBLIC, cidrMask: 24 },
        { name: "Isolated", subnetType: ec2.SubnetType.PRIVATE_ISOLATED, cidrMask: 24 },
      ],
    });

    // VPC endpoint for Secrets Manager (avoids NAT)
    vpc.addInterfaceEndpoint("SecretsManagerEndpoint", {
      service: ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
    });

    // VPC endpoint for Bedrock Runtime (avoids NAT, keeps traffic on AWS backbone)
    if (isBedrock) {
      vpc.addInterfaceEndpoint("BedrockRuntimeEndpoint", {
        service: new ec2.InterfaceVpcEndpointService(
          `com.amazonaws.${this.region}.bedrock-runtime`
        ),
      });
    }

    // ── RDS PostgreSQL ─────────────────────────────────────────────────
    const dbSg = new ec2.SecurityGroup(this, "DbSg", { vpc });
    const db = new rds.DatabaseInstance(this, "Postgres", {
      engine: rds.DatabaseInstanceEngine.postgres({ version: rds.PostgresEngineVersion.VER_17 }),
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T4G, ec2.InstanceSize.MICRO),
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      securityGroups: [dbSg],
      databaseName: "opencompany",
      credentials: rds.Credentials.fromGeneratedSecret("opencompany"),
      removalPolicy: cdk.RemovalPolicy.SNAPSHOT,
    });

    // ── Secrets Manager ────────────────────────────────────────────────
    const appSecret = new secretsmanager.Secret(this, "AppSecret", {
      secretName: "opencompany/app-config",
      generateSecretString: {
        secretStringTemplate: JSON.stringify({
          TELEGRAM_BOT_TOKEN: "CHANGE_ME",
          API_KEY: "CHANGE_ME",
          ...(isBedrock
            ? {}
            : {
                OPENAI_API_KEY: "CHANGE_ME",
                OPENAI_API_BASE: "https://api.openai.com",
                LITELLM_MODEL_ID: "gpt-4",
              }),
        }),
        generateStringKey: "_generated",
      },
    });

    // ── ECS Cluster ────────────────────────────────────────────────────
    const cluster = new ecs.Cluster(this, "Cluster", { vpc });

    // ── Docker image ───────────────────────────────────────────────────
    const image = new ecr_assets.DockerImageAsset(this, "AppImage", {
      directory: "..", // repo root
      platform: ecr_assets.Platform.LINUX_AMD64,
      exclude: [
        "infra",
        "docs",
        ".git",
        ".github",
        "tests",
        "workspaces",
        ".venv",
        ".ruff_cache",
        ".pytest_cache",
        "*.egg-info",
      ],
    });

    // ── Task definition ────────────────────────────────────────────────
    const taskDef = new ecs.FargateTaskDefinition(this, "TaskDef", {
      cpu: 256,
      memoryLimitMiB: 512,
    });

    // Bedrock IAM policy — allows the ECS task to call Bedrock models
    // Uses wildcard resources to cover both foundation-model and inference-profile ARNs
    // (cross-region model IDs like us.anthropic.* use inference profiles)
    if (isBedrock) {
      taskDef.addToTaskRolePolicy(
        new iam.PolicyStatement({
          sid: "AllowBedrockInvoke",
          effect: iam.Effect.ALLOW,
          actions: [
            "bedrock:InvokeModel",
            "bedrock:InvokeModelWithResponseStream",
          ],
          resources: [
            `arn:aws:bedrock:${this.region}::foundation-model/*`,
            `arn:aws:bedrock:${this.region}:${this.account}:inference-profile/*`,
          ],
        })
      );
    }

    // Grant Secrets Manager read
    appSecret.grantRead(taskDef.taskRole);
    db.secret?.grantRead(taskDef.taskRole);

    // ── Log group ──────────────────────────────────────────────────────
    const logGroup = new logs.LogGroup(this, "AppLogs", {
      logGroupName: "/aws/ecs/opencompany",
      retention: logs.RetentionDays.TWO_WEEKS,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // ── Build environment variables ────────────────────────────────────
    const environment: Record<string, string> = {
      LOG_LEVEL: "INFO",
      REDIS_URL: "redis://localhost:6379/0", // Redis sidecar
    };

    if (isBedrock) {
      const bedrockModel = BEDROCK_MODELS[props.modelProvider];
      environment["MODEL_PROVIDER"] = "bedrock";
      environment["BEDROCK_MODEL_ID"] = bedrockModel?.envModelId ?? "";
      environment["AWS_REGION"] = this.region;
    } else {
      environment["MODEL_PROVIDER"] = "litellm";
    }

    // ── App container ──────────────────────────────────────────────────
    const appContainer = taskDef.addContainer("app", {
      image: ecs.ContainerImage.fromDockerImageAsset(image),
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: "app", logGroup }),
      environment,
      secrets: {
        // Inject secrets from Secrets Manager as env vars
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
      healthCheck: {
        // Mirrors the Dockerfile HEALTHCHECK — start-period covers lifespan startup
        // (DB migrations, persona seeding) which can take up to 90s on cold start.
        command: ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
        startPeriod: cdk.Duration.seconds(120),
        retries: 3,
      },
      portMappings: [{ containerPort: 8000 }],
    });

    // Inject DATABASE_URL from RDS secret
    if (db.secret) {
      appContainer.addSecret(
        "DB_HOST",
        ecs.Secret.fromSecretsManager(db.secret, "host")
      );
      appContainer.addSecret(
        "DB_PORT",
        ecs.Secret.fromSecretsManager(db.secret, "port")
      );
      appContainer.addSecret(
        "DB_USER",
        ecs.Secret.fromSecretsManager(db.secret, "username")
      );
      appContainer.addSecret(
        "DB_PASSWORD",
        ecs.Secret.fromSecretsManager(db.secret, "password")
      );
      appContainer.addEnvironment("DB_NAME", "opencompany");
    }

    // ── Redis sidecar ──────────────────────────────────────────────────
    taskDef.addContainer("redis", {
      image: ecs.ContainerImage.fromRegistry("redis:7-alpine"),
      memoryLimitMiB: 128,
      essential: false,
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: "redis", logGroup }),
      portMappings: [{ containerPort: 6379 }],
    });

    // ── Security group for ECS ─────────────────────────────────────────
    const ecsSg = new ec2.SecurityGroup(this, "EcsSg", { vpc });
    dbSg.addIngressRule(ecsSg, ec2.Port.tcp(5432), "ECS to RDS");

    // ── Cloud Map namespace (for API Gateway VPC Link integration) ─────
    const namespace = new servicediscovery.PrivateDnsNamespace(this, "Namespace", {
      name: "opencompany.local",
      vpc,
    });

    // ── Fargate service ────────────────────────────────────────────────
    const service = new ecs.FargateService(this, "Service", {
      cluster,
      taskDefinition: taskDef,
      desiredCount: 1,
      assignPublicIp: true,
      vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC },
      securityGroups: [ecsSg],
      enableExecuteCommand: true,
      cloudMapOptions: {
        name: "app",
        cloudMapNamespace: namespace,
        containerPort: 8000,
      },
    });

    // ── Ingress ────────────────────────────────────────────────────────
    if (props.useAlb) {
      const alb = new elbv2.ApplicationLoadBalancer(this, "Alb", {
        vpc,
        internetFacing: true,
      });
      const listener = alb.addListener("Http", { port: 80 });
      listener.addTargets("EcsTarget", {
        port: 8000,
        targets: [service],
        healthCheck: { path: "/health" },
      });
      ecsSg.addIngressRule(
        ec2.Peer.securityGroupId(alb.connections.securityGroups[0].securityGroupId),
        ec2.Port.tcp(8000),
        "ALB to ECS"
      );
      new cdk.CfnOutput(this, "AppUrl", { value: `http://${alb.loadBalancerDnsName}` });
    } else {
      // API Gateway HTTP API
      const api = new apigwv2.CfnApi(this, "HttpApi", {
        name: "OpenCompanyApi",
        protocolType: "HTTP",
      });

      const vpcLink = new apigwv2.CfnVpcLink(this, "VpcLink", {
        name: "OpenCompanyVpcLink",
        subnetIds: vpc.publicSubnets.map((s) => s.subnetId),
        securityGroupIds: [ecsSg.securityGroupId],
      });

      // Allow inbound from API GW via VPC Link
      ecsSg.addIngressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(8000), "API GW to ECS");

      const integration = new apigwv2.CfnIntegration(this, "Integration", {
        apiId: api.ref,
        integrationType: "HTTP_PROXY",
        integrationUri: service.cloudMapService!.serviceArn,
        integrationMethod: "ANY",
        connectionType: "VPC_LINK",
        connectionId: vpcLink.ref,
        payloadFormatVersion: "1.0",
      });

      new apigwv2.CfnRoute(this, "DefaultRoute", {
        apiId: api.ref,
        routeKey: "$default",
        target: `integrations/${integration.ref}`,
      });

      const stage = new apigwv2.CfnStage(this, "DefaultStage", {
        apiId: api.ref,
        stageName: "$default",
        autoDeploy: true,
      });

      new cdk.CfnOutput(this, "AppUrl", {
        value: `https://${api.ref}.execute-api.${this.region}.amazonaws.com`,
      });
    }

    // ── Outputs ────────────────────────────────────────────────────────
    new cdk.CfnOutput(this, "EcsCluster", { value: cluster.clusterName });
    new cdk.CfnOutput(this, "ModelProvider", { value: props.modelProvider });
    new cdk.CfnOutput(this, "SecretArn", { value: appSecret.secretArn });
  }
}
