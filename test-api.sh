#!/bin/bash

# Configuration - Easy to change if running in Docker or Staging
HOST=${1:-"localhost:8080"}
ENDPOINT="http://$HOST/api/v1/trees/level-order"

echo "==============================================="
echo "Target: $ENDPOINT"
echo "==============================================="

# 1. Happy Path
echo -e "\n[TEST 1] Standard Binary Tree"
curl -X POST "$ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{
    "value": 1,
    "left": { "value": 2, "left": { "value": 4 }, "right": { "value": 5 } },
    "right": { "value": 3, "right": { "value": 6 } }
  }' \
  -i | grep -E "HTTP/1.1|X-Runtime|\[\["

# 2. Null Body (Validation Test)
echo -e "\n[TEST 2] Null Body (Expected: 400 Bad Request)"
curl -X POST "$ENDPOINT" \
  -H "Content-Type: application/json" \
  -d 'null' \
  -i | grep -E "HTTP/1.1|error"

# 3. Malformed JSON (Framework Resilience)
echo -e "\n[TEST 3] Malformed JSON (Expected: 400 or 415)"
curl -X POST "$ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{"value": 1, "left": "invalid_type"}' \
  -i | grep "HTTP/1.1"

# 4. Empty Object
echo -e "\n[TEST 4] Empty Object {}"
curl -X POST "$ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{}' \
  -i | grep "HTTP/1.1"

echo -e "\n==============================================="
echo "Tests Completed"
