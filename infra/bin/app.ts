#!/usr/bin/env node
import * as cdk from "aws-cdk-lib";
import { OpenCompanyStack } from "../lib/opencompany-stack";

const app = new cdk.App();

const useAlb = app.node.tryGetContext("use_alb") === "true";
const modelProvider = app.node.tryGetContext("model_provider") ?? "external";

new OpenCompanyStack(app, "OpenCompanyStack", {
  useAlb,
  modelProvider,
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION || "eu-west-1",
  },
});

app.synth();
