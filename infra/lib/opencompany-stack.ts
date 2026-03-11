/**
 * OpenCompany AWS CDK stack.
 *
 * Deploys: VPC | RDS Postgres | ECS Fargate (app + Redis sidecar) | ingress.
 *
 * Usage:
 *   cd infra && npm install
 *   npx cdk bootstrap                  # first time only
 *   npx cdk deploy                     # API Gateway HTTP API (default, ~$28/mo)
 *   npx cdk deploy -c use_alb=true     # ALB instead (~$43/mo)
 */

import * as cdk from "aws-cdk-lib";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as ecs from "aws-cdk-lib/aws-ecs";
import * as ecs_patterns from "aws-cdk-lib/aws-ecs-patterns";
import * as iam from "aws-cdk-lib/aws-iam";
import * as rds from "aws-cdk-lib/aws-rds";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import * as logs from "aws-cdk-lib/aws-logs";
import * as ecr_assets from "aws-cdk-lib/aws-ecr-assets";
import * as apigwv2 from "aws-cdk-lib/aws-apigatewayv2";
import * as sd from "aws-cdk-lib/aws-servicediscovery";
import { Construct } from "constructs";
import * as path from "path";

/** Supported model providers. Bedrock options use IAM auth (no API key needed). */
type ModelProvider = "bedrock-anthropic" | "bedrock-nova" | "external";

const BEDROCK_MODELS: Record<string, string> = {
  "bedrock-anthropic": "bedrock/anthropic.claude-sonnet-4-20250514-v1:0",
  "bedrock-nova": "bedrock/amazon.nova-pro-v1:0",
};

export interface OpenCompanyStackProps extends cdk.StackProps {
  useAlb?: boolean;
  modelProvider?: ModelProvider;
}

export class OpenCompanyStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: OpenCompanyStackProps) {
    super(scope, id, props);

    const useAlb = props.useAlb ?? false;
    const modelProvider: ModelProvider = props.modelProvider ?? "external";
    const useBedrock = modelProvider.startsWith("bedrock");

    // ------------------------------------------------------------------ //
    // VPC — 2 AZs, public + isolated subnets, NO NAT (saves ~$32/mo)
    // ------------------------------------------------------------------ //
    const vpc = new ec2.Vpc(this, "Vpc", {
      maxAzs: 2,
      natGateways: 0,
      subnetConfiguration: [
        {
          name: "Public",
          subnetType: ec2.SubnetType.PUBLIC,
          cidrMask: 24,
        },
        {
          name: "Isolated",
          subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
          cidrMask: 24,
        },
      ],
    });

    // VPC endpoint for Secrets Manager (Fargate in public subnets needs this)
    vpc.addInterfaceEndpoint("SecretsManagerEndpoint", {
      service: ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
    });

    // ------------------------------------------------------------------ //
    // Security groups
    // ------------------------------------------------------------------ //
    const appSg = new ec2.SecurityGroup(this, "AppSg", {
      vpc,
      description: "Fargate app",
    });

    const dbSg = new ec2.SecurityGroup(this, "DbSg", {
      vpc,
      description: "RDS Postgres",
    });
    dbSg.addIngressRule(appSg, ec2.Port.tcp(5432), "Fargate -> Postgres");

    // ------------------------------------------------------------------ //
    // RDS PostgreSQL t4g.micro (single-AZ, ~$14/mo)
    // ------------------------------------------------------------------ //
    const db = new rds.DatabaseInstance(this, "Database", {
      engine: rds.DatabaseInstanceEngine.postgres({
        version: rds.PostgresEngineVersion.VER_17,
      }),
      instanceType: ec2.InstanceType.of(
        ec2.InstanceClass.T4G,
        ec2.InstanceSize.MICRO
      ),
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      securityGroups: [dbSg],
      credentials: rds.Credentials.fromGeneratedSecret("opencompany"),
      databaseName: "opencompany",
      allocatedStorage: 20,
      maxAllocatedStorage: 50,
      removalPolicy: cdk.RemovalPolicy.SNAPSHOT,
      deletionProtection: false,
      backupRetention: cdk.Duration.days(7),
    });

    // ------------------------------------------------------------------ //
    // App secrets (populate via AWS console / CLI after first deploy)
    // ------------------------------------------------------------------ //
    const secretValues: Record<string, cdk.SecretValue> = {
      TELEGRAM_BOT_TOKEN: cdk.SecretValue.unsafePlainText("changeme"),
      API_KEY: cdk.SecretValue.unsafePlainText("changeme"),
    };
    if (!useBedrock) {
      // External provider (OpenAI, LiteLLM proxy, etc.) — needs API key
      secretValues.OPENAI_API_KEY =
        cdk.SecretValue.unsafePlainText("changeme");
      secretValues.OPENAI_API_BASE = cdk.SecretValue.unsafePlainText(
        "https://api.openai.com"
      );
      secretValues.LITELLM_MODEL_ID =
        cdk.SecretValue.unsafePlainText("gpt-4");
    }

    const appSecrets = new secretsmanager.Secret(this, "AppSecrets", {
      secretName: "opencompany/app-config",
      secretObjectValue: secretValues,
    });

    // ------------------------------------------------------------------ //
    // Docker image (built from project Dockerfile, pushed to ECR)
    // ------------------------------------------------------------------ //
    const imageAsset = new ecr_assets.DockerImageAsset(this, "AppImage", {
      directory: path.join(__dirname, "../.."), // project root
      exclude: [
        "infra",
        ".venv",
        ".git",
        ".playwright-mcp",
        "node_modules",
        "__pycache__",
        "*.pyc",
      ],
    });

    // ------------------------------------------------------------------ //
    // ECS cluster + Fargate task definition
    // ------------------------------------------------------------------ //
    const cluster = new ecs.Cluster(this, "Cluster", { vpc });

    const taskDef = new ecs.FargateTaskDefinition(this, "TaskDef", {
      cpu: 256,
      memoryLimitMiB: 512,
    });

    // Redis sidecar (ephemeral — fine for pub/sub event bus)
    const redisContainer = taskDef.addContainer("redis", {
      image: ecs.ContainerImage.fromRegistry("redis:7-alpine"),
      portMappings: [{ containerPort: 6379 }],
      logging: ecs.LogDrivers.awsLogs({
        streamPrefix: "redis",
        logRetention: logs.RetentionDays.ONE_WEEK,
      }),
      healthCheck: {
        command: ["CMD", "redis-cli", "ping"],
        interval: cdk.Duration.seconds(10),
        timeout: cdk.Duration.seconds(3),
        retries: 3,
      },
    });

    // App container — environment varies by model provider
    const appEnv: Record<string, string> = {
      DB_HOST: db.dbInstanceEndpointAddress,
      DB_PORT: db.dbInstanceEndpointPort,
      DB_NAME: "opencompany",
      REDIS_URL: "redis://localhost:6379/0",
      LOG_LEVEL: "INFO",
      CEO_KICKOFF_INTERVAL_SECONDS: "0",
      HEARTBEAT_INTERVAL_SECONDS: "0",
    };

    if (useBedrock) {
      // Bedrock uses IAM auth — no API key needed. LiteLLM reads AWS creds
      // from the environment automatically (ECS task role).
      appEnv.LITELLM_MODEL_ID = BEDROCK_MODELS[modelProvider];
      appEnv.AWS_REGION_NAME = cdk.Stack.of(this).region;
    }

    const appContainerSecrets: Record<string, ecs.Secret> = {
      DB_USER: ecs.Secret.fromSecretsManager(db.secret!, "username"),
      DB_PASSWORD: ecs.Secret.fromSecretsManager(db.secret!, "password"),
      TELEGRAM_BOT_TOKEN: ecs.Secret.fromSecretsManager(
        appSecrets,
        "TELEGRAM_BOT_TOKEN"
      ),
      API_KEY: ecs.Secret.fromSecretsManager(appSecrets, "API_KEY"),
    };

    if (!useBedrock) {
      // External provider needs API key, base URL, and model ID from secrets
      appContainerSecrets.OPENAI_API_KEY = ecs.Secret.fromSecretsManager(
        appSecrets,
        "OPENAI_API_KEY"
      );
      appContainerSecrets.OPENAI_API_BASE = ecs.Secret.fromSecretsManager(
        appSecrets,
        "OPENAI_API_BASE"
      );
      appContainerSecrets.LITELLM_MODEL_ID = ecs.Secret.fromSecretsManager(
        appSecrets,
        "LITELLM_MODEL_ID"
      );
    }

    const appContainer = taskDef.addContainer("app", {
      image: ecs.ContainerImage.fromDockerImageAsset(imageAsset),
      portMappings: [{ containerPort: 8000, name: "app" }],
      environment: appEnv,
      secrets: appContainerSecrets,
      logging: ecs.LogDrivers.awsLogs({
        streamPrefix: "opencompany",
        logRetention: logs.RetentionDays.TWO_WEEKS,
      }),
    });

    // Grant Bedrock invoke permissions to the task role
    if (useBedrock) {
      taskDef.taskRole.addToPrincipalPolicy(
        new iam.PolicyStatement({
          actions: ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
          resources: ["arn:aws:bedrock:*::foundation-model/*"],
        })
      );
    }

    appContainer.addContainerDependencies({
      container: redisContainer,
      condition: ecs.ContainerDependencyCondition.HEALTHY,
    });

    // ------------------------------------------------------------------ //
    // Ingress: ALB (opt-in) or API Gateway HTTP API (default)
    // ------------------------------------------------------------------ //
    if (useAlb) {
      this.createAlbIngress(vpc, cluster, taskDef, appSg);
    } else {
      this.createApiGwIngress(vpc, cluster, taskDef, appSg);
    }

    // ------------------------------------------------------------------ //
    // Outputs
    // ------------------------------------------------------------------ //
    new cdk.CfnOutput(this, "DbSecretArn", {
      value: db.secret!.secretArn,
    });
    new cdk.CfnOutput(this, "AppSecretsArn", {
      value: appSecrets.secretArn,
    });
    new cdk.CfnOutput(this, "EcsCluster", {
      value: cluster.clusterName,
    });
  }

  // ==================================================================== //
  // ALB mode — uses ecs-patterns L3 construct (~$43/mo total)
  // ==================================================================== //
  private createAlbIngress(
    vpc: ec2.Vpc,
    cluster: ecs.Cluster,
    taskDef: ecs.FargateTaskDefinition,
    appSg: ec2.SecurityGroup
  ) {
    const service =
      new ecs_patterns.ApplicationLoadBalancedFargateService(
        this,
        "Service",
        {
          cluster,
          taskDefinition: taskDef,
          assignPublicIp: true,
          taskSubnets: { subnetType: ec2.SubnetType.PUBLIC },
          publicLoadBalancer: true,
          desiredCount: 1,
          healthCheck: {
            command: [
              "CMD-SHELL",
              "curl -f http://localhost:8000/health || exit 1",
            ],
            interval: cdk.Duration.seconds(30),
            timeout: cdk.Duration.seconds(5),
            retries: 3,
            startPeriod: cdk.Duration.seconds(60),
          },
        }
      );

    service.targetGroup.configureHealthCheck({
      path: "/health",
      interval: cdk.Duration.seconds(30),
      healthyThresholdCount: 2,
    });

    service.service.connections.addSecurityGroup(appSg);

    new cdk.CfnOutput(this, "AppUrl", {
      value: `http://${service.loadBalancer.loadBalancerDnsName}`,
    });
  }

  // ==================================================================== //
  // API Gateway HTTP API mode — VPC Link + Cloud Map (~$28/mo total)
  // ==================================================================== //
  private createApiGwIngress(
    vpc: ec2.Vpc,
    cluster: ecs.Cluster,
    taskDef: ecs.FargateTaskDefinition,
    appSg: ec2.SecurityGroup
  ) {
    // Cloud Map namespace for service discovery
    const namespace = new sd.PrivateDnsNamespace(this, "Namespace", {
      name: "opencompany.local",
      vpc,
    });

    const service = new ecs.FargateService(this, "Service", {
      cluster,
      taskDefinition: taskDef,
      desiredCount: 1,
      assignPublicIp: true,
      vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC },
      securityGroups: [appSg],
      cloudMapOptions: {
        cloudMapNamespace: namespace,
        name: "app",
        containerPort: 8000,
      },
    });

    // VPC Link security group
    const vpcLinkSg = new ec2.SecurityGroup(this, "VpcLinkSg", {
      vpc,
      description: "API GW VPC Link",
    });
    appSg.addIngressRule(
      vpcLinkSg,
      ec2.Port.tcp(8000),
      "VPC Link -> App"
    );

    // VPC Link (L1 — always stable, no alpha dependency)
    const vpcLink = new apigwv2.CfnVpcLink(this, "VpcLink", {
      name: "opencompany-vpclink",
      subnetIds: vpc.publicSubnets.map((s) => s.subnetId),
      securityGroupIds: [vpcLinkSg.securityGroupId],
    });

    // HTTP API
    const httpApi = new apigwv2.CfnApi(this, "HttpApi", {
      name: "opencompany-api",
      protocolType: "HTTP",
    });

    // Integration: HTTP_PROXY via VPC Link -> Cloud Map service
    const integration = new apigwv2.CfnIntegration(
      this,
      "ApiIntegration",
      {
        apiId: httpApi.ref,
        integrationType: "HTTP_PROXY",
        integrationUri: service.cloudMapService!.serviceArn,
        integrationMethod: "ANY",
        connectionType: "VPC_LINK",
        connectionId: vpcLink.ref,
        payloadFormatVersion: "1.0",
      }
    );

    // Default catch-all route
    new apigwv2.CfnRoute(this, "DefaultRoute", {
      apiId: httpApi.ref,
      routeKey: "$default",
      target: cdk.Fn.join("", ["integrations/", integration.ref]),
    });

    // Auto-deploy stage
    new apigwv2.CfnStage(this, "ApiStage", {
      apiId: httpApi.ref,
      stageName: "$default",
      autoDeploy: true,
    });

    new cdk.CfnOutput(this, "AppUrl", {
      value: cdk.Fn.join("", ["https://", httpApi.attrApiEndpoint]),
    });
  }
}
