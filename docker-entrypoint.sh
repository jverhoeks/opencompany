#!/bin/sh
# Conditionally wrap uvicorn with OpenTelemetry auto-instrumentation.
# Set OTEL_ENABLED=true and OTEL_EXPORTER_OTLP_ENDPOINT to enable tracing.

if [ "$OTEL_ENABLED" = "true" ]; then
    echo "OpenTelemetry enabled: service=$OTEL_SERVICE_NAME endpoint=$OTEL_EXPORTER_OTLP_ENDPOINT"
    exec opentelemetry-instrument uvicorn opencompany.main:app --host 0.0.0.0 --port 8000
else
    exec uvicorn opencompany.main:app --host 0.0.0.0 --port 8000
fi
