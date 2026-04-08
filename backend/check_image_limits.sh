#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >/tmp/zzdh-limit-test.log 2>&1 &
pid=$!
cleanup() {
  kill "$pid" >/dev/null 2>&1 || true
}
trap cleanup EXIT

sleep 2

echo "== zero image =="
curl -s -X POST http://127.0.0.1:8000/api/video-tasks \
  -F model_id=wan_i2v \
  -F token=test-token \
  -F prompt=test
echo

cat >/tmp/zzdh-img-a.txt <<'EOF'
fake image a
EOF
cat >/tmp/zzdh-img-b.txt <<'EOF'
fake image b
EOF

echo "== two images =="
curl -s -X POST http://127.0.0.1:8000/api/video-tasks \
  -F model_id=wan_i2v \
  -F token=test-token \
  -F prompt=test \
  -F files=@/tmp/zzdh-img-a.txt\;type=image/png \
  -F files=@/tmp/zzdh-img-b.txt\;type=image/png
echo
