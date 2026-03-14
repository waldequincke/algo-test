#!/bin/bash
# ══════════════════════════════════════════════════════════════════════════════
#  Create all 7 App Runner services from ECR images.
#
#  Prerequisites:
#    - All ECR images pushed (run ./deploy.sh all first)
#    - IAM role AppRunnerECRAccessRole must exist (run ./setup-iam.sh first)
#
#  Usage:
#    ./create-apprunner-services.sh
#
#  Re-running is safe: skips services that already exist (RUNNING or DEPLOYING).
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -f "${SCRIPT_DIR}/aws.env" ]; then
    echo "Error: aws.env not found"; exit 1
fi
set -a; source "${SCRIPT_DIR}/aws.env"; set +a

ACCESS_ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/AppRunnerECRAccessRole"
CPU="1 vCPU"
MEMORY="2 GB"

# ── Service definitions ────────────────────────────────────────────────────────
# Format: "name:port"
SERVICES=(
    "java:8080"
    "kotlin:8081"
    "spring:8084"
    "nodejs:8082"
    "nodejs-wt:8083"
    "python:8085"
    "go:8086"
)

# ── Helpers ────────────────────────────────────────────────────────────────────
service_exists() {
    local svc_name="$1"
    aws apprunner list-services --region "${AWS_REGION}" \
        --query "ServiceSummaryList[?ServiceName=='${svc_name}'].Status" \
        --output text 2>/dev/null | grep -qE "RUNNING|DEPLOYING|OPERATION_IN_PROGRESS"
}

# Health check config per service:
#   Quarkus (java, kotlin)  → HTTP /q/health
#   Spring Boot             → HTTP /actuator/health
#   Python (FastAPI)        → HTTP /health
#   Go, Node.js             → TCP  (no dedicated health endpoint)
health_check_config() {
    local name="$1"
    case "$name" in
        java|kotlin)
            echo '{"Protocol":"HTTP","Path":"/q/health","Interval":10,"Timeout":5,"HealthyThreshold":1,"UnhealthyThreshold":5}'
            ;;
        spring)
            echo '{"Protocol":"HTTP","Path":"/actuator/health","Interval":10,"Timeout":5,"HealthyThreshold":1,"UnhealthyThreshold":5}'
            ;;
        python)
            echo '{"Protocol":"HTTP","Path":"/health","Interval":10,"Timeout":5,"HealthyThreshold":1,"UnhealthyThreshold":5}'
            ;;
        *)
            # Go, nodejs, nodejs-wt — TCP port check
            echo '{"Protocol":"TCP","Interval":10,"Timeout":5,"HealthyThreshold":1,"UnhealthyThreshold":5}'
            ;;
    esac
}

create_service() {
    local name="$1"
    local port="$2"
    local svc_name="tree-service-${name}"
    local image_uri="${ECR_URL}/tree-service-${name}:${IMAGE_TAG}"
    local hc
    hc=$(health_check_config "$name")

    echo ""
    echo "──────────────────────────────────────────────────────"
    echo "  Creating: ${svc_name}  (port ${port})"
    echo "  Image   : ${image_uri}"
    echo "──────────────────────────────────────────────────────"

    if service_exists "${svc_name}"; then
        echo "  ✓ Already exists — skipping"
        return
    fi

    local result
    result=$(aws apprunner create-service \
        --region "${AWS_REGION}" \
        --service-name "${svc_name}" \
        --source-configuration "{
            \"ImageRepository\": {
                \"ImageIdentifier\": \"${image_uri}\",
                \"ImageRepositoryType\": \"ECR\",
                \"ImageConfiguration\": {
                    \"Port\": \"${port}\",
                    \"RuntimeEnvironmentVariables\": {
                        \"TREE_MAX_DEPTH\": \"500\",
                        \"TREE_MAX_NODES\": \"10000\"
                    }
                }
            },
            \"AutoDeploymentsEnabled\": true,
            \"AuthenticationConfiguration\": {
                \"AccessRoleArn\": \"${ACCESS_ROLE_ARN}\"
            }
        }" \
        --instance-configuration "{
            \"Cpu\": \"${CPU}\",
            \"Memory\": \"${MEMORY}\"
        }" \
        --health-check-configuration "${hc}" \
        --query "Service.{ServiceUrl:ServiceUrl,Status:Status}" \
        --output json 2>&1)

    local url
    url=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('ServiceUrl','?'))" 2>/dev/null || echo "?")
    echo "  ✓ Created — URL: ${url}"
    echo "    (App Runner is provisioning — takes ~2-3 min to reach RUNNING)"
}

# ── Main ───────────────────────────────────────────────────────────────────────
echo "╔══════════════════════════════════════════════════════════╗"
echo "║     Create App Runner Services — Heptatlón               ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo "Account : ${AWS_ACCOUNT_ID}"
echo "Region  : ${AWS_REGION}"
echo "Role    : ${ACCESS_ROLE_ARN}"
echo ""

for entry in "${SERVICES[@]}"; do
    name="${entry%%:*}"
    port="${entry##*:}"
    create_service "$name" "$port"
done

echo ""
echo "══════════════════════════════════════════════════════════"
echo " All services submitted. Waiting for RUNNING state..."
echo "══════════════════════════════════════════════════════════"
echo ""
echo "Check status with:"
echo "  aws apprunner list-services --region ${AWS_REGION} \\"
echo "    --query 'ServiceSummaryList[].{Name:ServiceName,Status:Status,URL:ServiceUrl}' \\"
echo "    --output table"
echo ""
echo "Once all are RUNNING, update aws.env with the new ServiceUrls."
