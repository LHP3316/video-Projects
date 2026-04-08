#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >/tmp/zzdh-demo.log 2>&1 &
pid=$!

cleanup() {
  kill "$pid" >/dev/null 2>&1 || true
}
trap cleanup EXIT

sleep 2

echo "== health =="
curl -s http://127.0.0.1:8000/api/health
echo

echo "== model tabs =="
curl -s http://127.0.0.1:8000/api/model-tabs >/tmp/zzdh-tabs.json
python3 - <<'PY'
import json
with open("/tmp/zzdh-tabs.json", "r", encoding="utf-8") as f:
    data = json.load(f)
for tab in data:
    print(tab["name"], "=>", ", ".join(model["name"] for model in tab["models"]))
PY

cat >/tmp/zzdh-task.json <<'JSON'
{
  "feature": "text_to_image",
  "model_id": "deepseek_image",
  "token": "demo-token-123456",
  "prompt": "雨夜街道，少年回头，电影感构图",
  "source_text": "",
  "parameters": {
    "count": 2
  }
}
JSON

echo "== create task with expected DeepSeek image warning =="
curl -s -X POST http://127.0.0.1:8000/api/tasks \
  -H "Content-Type: application/json" \
  --data-binary @/tmp/zzdh-task.json
echo
