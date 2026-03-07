#!/bin/bash

# 1. Cargar variables
if [ -f aws.env ]; then
    # 'set -a' export automatically all the variables defined bellow
    set -a
    source aws.env
    set +a
    echo "Variables loaded correctly from aws.env"
else
    echo "Error: File aws.env not found"
    exit 1
fi

# 2. Build (Architecture AMD64 for AWS)
echo "Building image for ${REPO_NAME}..."
docker build --platform linux/amd64 -t ${REPO_NAME} .

# 3. Login to AWS
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_URL}

echo "Pushing image to ECR..."
docker tag ${REPO_NAME}:${IMAGE_TAG} ${ECR_URL}/${REPO_NAME}:${IMAGE_TAG}
docker push ${ECR_URL}/${REPO_NAME}:${IMAGE_TAG}

echo "Deploy finished!"
