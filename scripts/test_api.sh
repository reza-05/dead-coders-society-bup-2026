#!/bin/bash
set -e

BASE_URL=${1:-"http://127.0.0.1:8000"}

echo "=========================================="
echo "Testing GridWise API at: $BASE_URL"
echo "=========================================="

echo -e "\n[1] Testing /health endpoint..."
curl -s -i -X GET "$BASE_URL/health"
echo ""

echo -e "\n[2] Testing /optimize-energy endpoint with sample payload..."
START_TIME=$(date +%s%N)
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}\n" -X POST "$BASE_URL/optimize-energy" \
  -H "Content-Type: application/json" \
  -d @sample_request.json)
END_TIME=$(date +%s%N)

DURATION=$(( (END_TIME - START_TIME) / 1000000 ))

HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS" | cut -d':' -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_STATUS/d')

echo "Status Code: $HTTP_STATUS"
echo "Duration: ${DURATION}ms"
echo "Response Body:"
echo "$BODY" | python3 -m json.tool || echo "$BODY"

echo -e "\n=========================================="
echo "Verification complete!"
echo "=========================================="
