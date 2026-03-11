#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import { OpenCompanyStack } from "../lib/opencompany-stack";

const app = new cdk.App();

const modelProvider = app.node.tryGetContext("model_provider") ?? "bedrock-anthropic";
const useAlb = app.node.tryGetContext("use_alb") === "true";

new OpenCompanyStack(app, "OpenCompanyStack", {
  modelProvider,
  useAlb,
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION ?? "us-east-1",
  },
});
