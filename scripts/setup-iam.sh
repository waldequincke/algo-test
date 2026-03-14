#!/bin/bash
# Creates all IAM roles and policies required to run the benchmark.
# Safe to run multiple times — checks for existing resources before creating.
#
# What it creates:
#
#   1. algo-ecr-push-policy          — lets your developer machine push images to ECR
#   2. algo-apprunner-access-role    — lets App Runner pull images from ECR
#      └── algo-apprunner-ecr-policy
#   3. algo-ec2-benchmark-role       — lets the EC2 benchmark client read CloudWatch
#      └── algo-ec2-benchmark-policy
#      └── algo-ec2-benchmark-instance-profile
#
# Usage:
#   ./setup-iam.sh
#   # Then attach the printed role/profile ARNs where instructed.
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IAM_DIR="${SCRIPT_DIR}/iam"

# ── Load AWS config ────────────────────────────────────────────────────────────
if [ ! -f "${SCRIPT_DIR}/aws.env" ]; then
    echo "Error: aws.env not found in ${SCRIPT_DIR}"
    exit 1
fi
set -a; source "${SCRIPT_DIR}/aws.env"; set +a

# Verify credentials
echo "Verifying AWS credentials..."
CALLER=$(aws sts get-caller-identity --output json)
CURRENT_ACCOUNT=$(echo "$CALLER" | grep -o '"Account": *"[^"]*"' | grep -o '"[^"]*"$' | tr -d '"')
echo "Account : ${CURRENT_ACCOUNT}  (expected: ${AWS_ACCOUNT_ID})"
echo "Region  : ${AWS_REGION}"
if [ "$CURRENT_ACCOUNT" != "$AWS_ACCOUNT_ID" ]; then
    echo "Error: account mismatch — check aws.env or run 'aws sso login'"
    exit 1
fi

# ── Helpers ────────────────────────────────────────────────────────────────────

# Render __REGION__ / __ACCOUNT_ID__ placeholders in a policy JSON file.
render_policy() {
    local file="$1"
    sed \
        -e "s|__REGION__|${AWS_REGION}|g" \
        -e "s|__ACCOUNT_ID__|${AWS_ACCOUNT_ID}|g" \
        "$file"
}

# Create or update an IAM policy; return its ARN.
ensure_policy() {
    local name="$1" file="$2"
    local arn="arn:aws:iam::${AWS_ACCOUNT_ID}:policy/${name}"
    local doc
    doc=$(render_policy "$file")

    if aws iam get-policy --policy-arn "$arn" > /dev/null 2>&1; then
        echo "  Policy exists — updating default version: ${name}" >&2
        # Delete all non-default versions first (max 5 versions allowed)
        local versions
        versions=$(aws iam list-policy-versions --policy-arn "$arn" \
            --query 'Versions[?IsDefaultVersion==`false`].VersionId' \
            --output text)
        for v in $versions; do
            aws iam delete-policy-version --policy-arn "$arn" --version-id "$v"
        done
        aws iam create-policy-version \
            --policy-arn "$arn" \
            --policy-document "$doc" \
            --set-as-default > /dev/null
    else
        echo "  Creating policy: ${name}" >&2
        aws iam create-policy \
            --policy-name "$name" \
            --policy-document "$doc" \
            --description "Algo benchmark — ${name}" \
            --tags Key=Project,Value=algo-benchmark \
            > /dev/null
    fi
    echo "$arn"
}

# Create an IAM role if it doesn't exist; attach it to a trust policy.
ensure_role() {
    local name="$1" trust_file="$2" description="$3"
    local trust_doc
    trust_doc=$(cat "$trust_file")

    if aws iam get-role --role-name "$name" > /dev/null 2>&1; then
        echo "  Role exists — updating trust policy: ${name}" >&2
        aws iam update-assume-role-policy \
            --role-name "$name" \
            --policy-document "$trust_doc" > /dev/null
    else
        echo "  Creating role: ${name}" >&2
        aws iam create-role \
            --role-name "$name" \
            --assume-role-policy-document "$trust_doc" \
            --description "$description" \
            --tags Key=Project,Value=algo-benchmark \
            > /dev/null
    fi
    aws iam get-role --role-name "$name" \
        --query 'Role.Arn' --output text
}

# Attach a policy to a role (idempotent).
attach_policy() {
    local role="$1" policy_arn="$2"
    if aws iam list-attached-role-policies --role-name "$role" \
            --query "AttachedPolicies[?PolicyArn=='${policy_arn}'].PolicyName" \
            --output text | grep -q .; then
        echo "  Policy already attached: $(basename "$policy_arn")"
    else
        echo "  Attaching policy: $(basename "$policy_arn")"
        aws iam attach-role-policy --role-name "$role" --policy-arn "$policy_arn"
    fi
}

# Create an EC2 instance profile and add the role to it (idempotent).
ensure_instance_profile() {
    local profile_name="$1" role_name="$2"

    if ! aws iam get-instance-profile --instance-profile-name "$profile_name" \
            > /dev/null 2>&1; then
        echo "  Creating instance profile: ${profile_name}" >&2
        aws iam create-instance-profile \
            --instance-profile-name "$profile_name" \
            --tags Key=Project,Value=algo-benchmark > /dev/null
    else
        echo "  Instance profile exists: ${profile_name}" >&2
    fi

    local attached
    attached=$(aws iam get-instance-profile \
        --instance-profile-name "$profile_name" \
        --query 'InstanceProfile.Roles[0].RoleName' \
        --output text 2>/dev/null || echo "None")

    if [ "$attached" = "$role_name" ]; then
        echo "  Role already in instance profile" >&2
    else
        if [ "$attached" != "None" ] && [ -n "$attached" ]; then
            echo "  Removing old role from profile: ${attached}" >&2
            aws iam remove-role-from-instance-profile \
                --instance-profile-name "$profile_name" \
                --role-name "$attached"
        fi
        echo "  Adding role to instance profile" >&2
        aws iam add-role-to-instance-profile \
            --instance-profile-name "$profile_name" \
            --role-name "$role_name"
    fi

    aws iam get-instance-profile \
        --instance-profile-name "$profile_name" \
        --query 'InstanceProfile.Arn' --output text
}

# ── 1. ECR push policy (developer machine) ────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════"
echo " 1/3  ECR push policy (developer machine)"
echo "═══════════════════════════════════════════════"
ECR_PUSH_POLICY_ARN=$(ensure_policy \
    "algo-ecr-push-policy" \
    "${IAM_DIR}/policy-ecr-push.json")
echo "  ARN: ${ECR_PUSH_POLICY_ARN}"
echo ""
echo "  Attach to your IAM user/role:"
echo "  aws iam attach-user-policy --user-name <YOU> --policy-arn ${ECR_PUSH_POLICY_ARN}"
echo "  (or add to your SSO permission set in the AWS Console)"

# ── 2. App Runner access role (ECR pull) ──────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════"
echo " 2/3  App Runner access role (ECR pull)"
echo "═══════════════════════════════════════════════"
APPRUNNER_ROLE_ARN=$(ensure_role \
    "algo-apprunner-access-role" \
    "${IAM_DIR}/trust-policy-apprunner.json" \
    "Allows App Runner to pull images from ECR for algo-benchmark")

APPRUNNER_POLICY_ARN=$(ensure_policy \
    "algo-apprunner-ecr-policy" \
    "${IAM_DIR}/policy-apprunner-ecr.json")

attach_policy "algo-apprunner-access-role" "$APPRUNNER_POLICY_ARN"
echo "  Role ARN: ${APPRUNNER_ROLE_ARN}"
echo ""
echo "  Use this ARN when creating each App Runner service:"
echo "  aws apprunner create-service ... --access-role-arn ${APPRUNNER_ROLE_ARN}"

# ── 3. EC2 benchmark role (CloudWatch read) ───────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════"
echo " 3/3  EC2 benchmark role (CloudWatch read)"
echo "═══════════════════════════════════════════════"
EC2_ROLE_ARN=$(ensure_role \
    "algo-ec2-benchmark-role" \
    "${IAM_DIR}/trust-policy-ec2.json" \
    "Allows EC2 benchmark client to read CloudWatch metrics for algo-benchmark")

EC2_POLICY_ARN=$(ensure_policy \
    "algo-ec2-benchmark-policy" \
    "${IAM_DIR}/policy-ec2-benchmark.json")

attach_policy "algo-ec2-benchmark-role" "$EC2_POLICY_ARN"

PROFILE_ARN=$(ensure_instance_profile \
    "algo-ec2-benchmark-profile" \
    "algo-ec2-benchmark-role")

echo "  Role ARN   : ${EC2_ROLE_ARN}"
echo "  Profile ARN: ${PROFILE_ARN}"

# ── Summary ────────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║  IAM setup complete — next steps                                     ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
cat <<SUMMARY

1. ATTACH the ECR push policy to your developer IAM user / SSO permission set:
   Policy ARN: ${ECR_PUSH_POLICY_ARN}

2. RUN deploy.sh to build and push all 5 images:
   ./scripts/deploy.sh all

3. CREATE 5 App Runner services (one per image) using:
   Access Role ARN: ${APPRUNNER_ROLE_ARN}

   Example for java:
   aws apprunner create-service \\
     --service-name tree-service-java \\
     --source-configuration '{
       "ImageRepository": {
         "ImageIdentifier": "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/tree-service-java:latest",
         "ImageRepositoryType": "ECR",
         "ImageConfiguration": {"Port": "8080"}
       },
       "AuthenticationConfiguration": {
         "AccessRoleArn": "${APPRUNNER_ROLE_ARN}"
       }
     }' \\
     --instance-configuration '{"Cpu":"1 vCPU","Memory":"2 GB"}' \\
     --health-check-configuration '{"Protocol":"HTTP","Path":"/q/health"}' \\
     --region ${AWS_REGION}

   Port mapping per service:
     java       → 8080   health: /q/health
     kotlin     → 8081   health: /q/health
     nodejs     → 8082   health: /actuator/health  (NestJS)
     nodejs-wt  → 8083   health: /actuator/health  (NestJS)
     spring     → 8084   health: /actuator/health

4. LAUNCH the EC2 benchmark client with the instance profile:
   Profile ARN: ${PROFILE_ARN}

   aws ec2 run-instances \\
     --image-id ami-0c101f26f147fa7fd \\
     --instance-type c7g.xlarge \\
     --iam-instance-profile Arn=${PROFILE_ARN} \\
     --subnet-id <same-subnet-as-apprunner> \\
     --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=algo-benchmark-client}]'

5. ON the EC2 instance:
   git clone <this-repo>
   cd algo-test
   ./scripts/setup-ec2.sh

   export JAVA_HOST=<java-apprunner-host>
   export KOTLIN_HOST=<kotlin-apprunner-host>
   export NODEJS_HOST=<nodejs-apprunner-host>
   export NODEJS_WT_HOST=<nodejs-wt-apprunner-host>
   export SPRING_HOST=<spring-apprunner-host>

   ./scripts/benchmark-aws.sh
SUMMARY
