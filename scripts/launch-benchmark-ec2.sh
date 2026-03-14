#!/bin/bash
# ══════════════════════════════════════════════════════════════════════════════
#  Launch EC2 benchmark client (t3.medium, Amazon Linux 2023, us-east-1)
#
#  Usage:
#    ./launch-benchmark-ec2.sh          # launch + print SSH command
#    ./launch-benchmark-ec2.sh --wait   # also wait until instance is ready
#
#  Prerequisites:
#    - aws CLI configured
#    - ~/.ssh/algo-benchmark.pem key pair exists in AWS us-east-1
#    - scripts/aws.env present
#
#  After launch:
#    1. SSH into the instance (command printed at the end)
#    2. Run: cd algo-test && git pull && pip3 install pandas matplotlib boto3
#    3. Run: python3 scripts/benchmark.py 2>&1 | tee benchmark.log
#    4. Run: scp ec2-user@<IP>:~/algo-test/benchmark_results_2026.csv .
#           scp ec2-user@<IP>:~/algo-test/probe_results_2026.csv .
#           scp ec2-user@<IP>:~/algo-test/cloudwatch_results_2026.csv .
#           scp ec2-user@<IP>:~/algo-test/benchmark.log .
#           scp -r ec2-user@<IP>:~/algo-test/images/*.png images/
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
set -a; source "${SCRIPT_DIR}/aws.env"; set +a

KEY_NAME="algo-benchmark"
KEY_FILE="${HOME}/.ssh/algo-benchmark.pem"
INSTANCE_TYPE="t3.medium"
AMI_AL2023=$(aws ec2 describe-images \
    --region "${AWS_REGION}" \
    --owners amazon \
    --filters \
        "Name=name,Values=al2023-ami-2023*-x86_64" \
        "Name=state,Values=available" \
    --query "sort_by(Images, &CreationDate)[-1].ImageId" \
    --output text)

WAIT_FLAG="${1:-}"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║     Launch EC2 Benchmark Client                          ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo "Region        : ${AWS_REGION}"
echo "Instance type : ${INSTANCE_TYPE}  (2 vCPU / 4 GB)"
echo "AMI           : ${AMI_AL2023}  (Amazon Linux 2023, latest)"
echo "Key pair      : ${KEY_NAME}"
echo ""

# ── Security group — allow SSH inbound ────────────────────────────────────────
SG_NAME="algo-benchmark-sg"
SG_ID=$(aws ec2 describe-security-groups \
    --region "${AWS_REGION}" \
    --filters "Name=group-name,Values=${SG_NAME}" \
    --query "SecurityGroups[0].GroupId" \
    --output text 2>/dev/null)

if [ "${SG_ID}" = "None" ] || [ -z "${SG_ID}" ]; then
    echo "Creating security group: ${SG_NAME}..."
    SG_ID=$(aws ec2 create-security-group \
        --region "${AWS_REGION}" \
        --group-name "${SG_NAME}" \
        --description "Algo benchmark client — SSH only" \
        --query "GroupId" --output text)
    aws ec2 authorize-security-group-ingress \
        --region "${AWS_REGION}" \
        --group-id "${SG_ID}" \
        --protocol tcp --port 22 --cidr 0.0.0.0/0 > /dev/null
    echo "  ✓ Created: ${SG_ID}"
else
    echo "Security group exists: ${SG_ID}"
fi

# ── User-data: install wrk2 + python deps + clone repo ───────────────────────
USER_DATA=$(cat <<'USERDATA'
#!/bin/bash
set -e
cd /home/ec2-user

# System deps
dnf install -y git gcc make openssl-devel python3-pip jq

# wrk2 (build from source)
git clone https://github.com/giltene/wrk2.git
cd wrk2 && make -j4 && cp wrk2 /usr/local/bin/wrk2 && cd ..

# Python deps
pip3 install --user pandas matplotlib boto3

# Clone repo
git clone https://github.com/waldequincke/algo-test.git algo-test 2>/dev/null || true
chown -R ec2-user:ec2-user /home/ec2-user

echo "SETUP COMPLETE" >> /home/ec2-user/setup.log
USERDATA
)

# ── Launch instance ────────────────────────────────────────────────────────────
echo "Launching ${INSTANCE_TYPE}..."
INSTANCE_JSON=$(aws ec2 run-instances \
    --region "${AWS_REGION}" \
    --image-id "${AMI_AL2023}" \
    --instance-type "${INSTANCE_TYPE}" \
    --key-name "${KEY_NAME}" \
    --security-group-ids "${SG_ID}" \
    --user-data "${USER_DATA}" \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=algo-benchmark-client}]" \
    --instance-initiated-shutdown-behavior terminate \
    --count 1)

INSTANCE_ID=$(echo "${INSTANCE_JSON}" | python3 -c "import sys,json; print(json.load(sys.stdin)['Instances'][0]['InstanceId'])")
echo "  ✓ Instance ID: ${INSTANCE_ID}"

# ── Wait for running + public IP ──────────────────────────────────────────────
echo "  Waiting for running state..."
aws ec2 wait instance-running --region "${AWS_REGION}" --instance-ids "${INSTANCE_ID}"
PUBLIC_IP=$(aws ec2 describe-instances \
    --region "${AWS_REGION}" \
    --instance-ids "${INSTANCE_ID}" \
    --query "Reservations[0].Instances[0].PublicIpAddress" \
    --output text)
echo "  ✓ Public IP: ${PUBLIC_IP}"

# ── Optionally wait for user-data setup to finish ─────────────────────────────
if [ "${WAIT_FLAG}" = "--wait" ]; then
    echo ""
    echo "Waiting for user-data setup to complete (~3-5 min)..."
    for i in $(seq 1 40); do
        sleep 15
        DONE=$(ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 \
            -i "${KEY_FILE}" "ec2-user@${PUBLIC_IP}" \
            "cat /home/ec2-user/setup.log 2>/dev/null" 2>/dev/null || echo "")
        echo -n "."
        if echo "${DONE}" | grep -q "SETUP COMPLETE"; then
            echo ""
            echo "  ✓ Setup complete"
            break
        fi
    done
fi

# ── Print next steps ──────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════════"
echo " EC2 READY"
echo "══════════════════════════════════════════════════════════"
echo ""
echo "SSH:"
echo "  ssh -i ~/.ssh/algo-benchmark.pem ec2-user@${PUBLIC_IP}"
echo ""
echo "Once connected, run:"
echo "  # Wait for setup.log to show SETUP COMPLETE:"
echo "  tail -f ~/setup.log"
echo ""
echo "  # Export service hosts and run benchmark:"
cat <<CMDS
  export JAVA_HOST=${JAVA_HOST}
  export KOTLIN_HOST=${KOTLIN_HOST}
  export SPRING_HOST=${SPRING_HOST}
  export NODEJS_HOST=${NODEJS_HOST}
  export NODEJS_WT_HOST=${NODEJS_WT_HOST}
  export PYTHON_HOST=${PYTHON_HOST}
  export GO_HOST=${GO_HOST}
  cd ~/algo-test
  git pull
  python3 scripts/benchmark.py 2>&1 | tee benchmark.log
CMDS
echo ""
echo "Copy results back:"
echo "  scp -i ~/.ssh/algo-benchmark.pem ec2-user@${PUBLIC_IP}:~/algo-test/benchmark_results_2026.csv ."
echo "  scp -i ~/.ssh/algo-benchmark.pem ec2-user@${PUBLIC_IP}:~/algo-test/probe_results_2026.csv ."
echo "  scp -i ~/.ssh/algo-benchmark.pem ec2-user@${PUBLIC_IP}:~/algo-test/cloudwatch_results_2026.csv ."
echo "  scp -i ~/.ssh/algo-benchmark.pem ec2-user@${PUBLIC_IP}:~/algo-test/benchmark.log ."
echo "  scp -i ~/.ssh/algo-benchmark.pem 'ec2-user@${PUBLIC_IP}:~/algo-test/images/*.png' images/"
echo ""
echo "Terminate when done:"
echo "  aws ec2 terminate-instances --region ${AWS_REGION} --instance-ids ${INSTANCE_ID}"
