#!/bin/bash
# Usage:
#   ./deploy.sh java          # deploy one service
#   ./deploy.sh all           # deploy all 5 services sequentially
#
# Each service is built for linux/amd64 (AWS) and pushed to its own ECR repo.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}/.."

# ── Load AWS config ────────────────────────────────────────────────────────────
if [ ! -f "${SCRIPT_DIR}/aws.env" ]; then
    echo "Error: aws.env not found in ${SCRIPT_DIR}"
    exit 1
fi
set -a; source "${SCRIPT_DIR}/aws.env"; set +a
echo "Config loaded: account=${AWS_ACCOUNT_ID} region=${AWS_REGION}"

# ── ECR helpers ────────────────────────────────────────────────────────────────
ecr_login() {
    echo "Logging in to ECR..."
    aws ecr get-login-password --region "${AWS_REGION}" | \
        docker login --username AWS --password-stdin "${ECR_URL}"
}

ecr_ensure_repo() {
    local repo="$1"
    if ! aws ecr describe-repositories --repository-names "$repo" \
            --region "${AWS_REGION}" > /dev/null 2>&1; then
        echo "Creating ECR repository: $repo"
        aws ecr create-repository \
            --repository-name "$repo" \
            --region "${AWS_REGION}" \
            --image-scanning-configuration scanOnPush=true \
            --image-tag-mutability MUTABLE > /dev/null
    else
        echo "ECR repository exists: $repo"
    fi
}

# ── Deploy one service ─────────────────────────────────────────────────────────
# Args: <service-name> <dockerfile-path-relative-to-ROOT> <build-context-absolute>
deploy_service() {
    local svc="$1"
    local dockerfile="$2"
    local context="$3"
    local repo="${REPO_NAME}-${svc}"

    echo ""
    echo "═══════════════════════════════════════════════════════"
    echo " Deploying: ${svc}  →  ${ECR_URL}/${repo}:${IMAGE_TAG}"
    echo "═══════════════════════════════════════════════════════"

    ecr_ensure_repo "$repo"

    echo "Building (linux/amd64)..."
    docker build \
        --platform linux/amd64 \
        -f "${dockerfile}" \
        -t "${repo}:${IMAGE_TAG}" \
        "${context}"

    echo "Tagging and pushing..."
    docker tag "${repo}:${IMAGE_TAG}" "${ECR_URL}/${repo}:${IMAGE_TAG}"
    docker push "${ECR_URL}/${repo}:${IMAGE_TAG}"

    echo "✓ ${svc} pushed → ${ECR_URL}/${repo}:${IMAGE_TAG}"
}

# ── Service definitions ────────────────────────────────────────────────────────
# Quarkus services: Dockerfile lives in impl dir, build context is repo root
# Node/Spring services: self-contained, build context is their own directory
deploy_java()      { deploy_service "java"      "${ROOT_DIR}/java-impl/Dockerfile"      "${ROOT_DIR}"; }
deploy_kotlin()    { deploy_service "kotlin"    "${ROOT_DIR}/kotlin-impl/Dockerfile"    "${ROOT_DIR}"; }
deploy_nodejs()    { deploy_service "nodejs"    "${ROOT_DIR}/nodejs-impl/Dockerfile"    "${ROOT_DIR}/nodejs-impl"; }
deploy_nodejswt()  { deploy_service "nodejs-wt" "${ROOT_DIR}/nodejs-wt-impl/Dockerfile" "${ROOT_DIR}/nodejs-wt-impl"; }
deploy_spring()    { deploy_service "spring"    "${ROOT_DIR}/spring-impl/Dockerfile"    "${ROOT_DIR}/spring-impl"; }
deploy_python()    { deploy_service "python"    "${ROOT_DIR}/python-impl/Dockerfile"    "${ROOT_DIR}/python-impl"; }
deploy_go()        { deploy_service "go"        "${ROOT_DIR}/go-impl/Dockerfile"        "${ROOT_DIR}/go-impl"; }

# ── Main ───────────────────────────────────────────────────────────────────────
SERVICE="${1:-}"
if [ -z "$SERVICE" ]; then
    echo "Usage: $0 [java|kotlin|nodejs|nodejs-wt|spring|python|go|all]"
    exit 1
fi

ecr_login

case "$SERVICE" in
    java)      deploy_java ;;
    kotlin)    deploy_kotlin ;;
    nodejs)    deploy_nodejs ;;
    nodejs-wt) deploy_nodejswt ;;
    spring)    deploy_spring ;;
    python)    deploy_python ;;
    go)        deploy_go ;;
    all)
        deploy_java
        deploy_kotlin
        deploy_nodejs
        deploy_nodejswt
        deploy_spring
        deploy_python
        deploy_go
        echo ""
        echo "✓ All 7 services deployed to ECR."
        ;;
    *)
        echo "Unknown service: $SERVICE"
        echo "Valid options: java kotlin nodejs nodejs-wt spring python go all"
        exit 1
        ;;
esac
