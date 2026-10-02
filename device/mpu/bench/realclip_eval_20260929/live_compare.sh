#!/bin/sh
# Side-by-side live comparison of the deployed champion and the 29 Sept candidates.
# Every minute: snapshot 5 frames spread across the live app's ring buffer, send the
# same frames to each model's own runner (ports 1340-1343, never the app's 1337), and
# append every box >= 0.05 to live.jsonl. Frames with any box are kept in hits/.
cd "$(dirname "$0")"
RING=$HOME/ArduinoApps/eletect-x/python/data/home_test/ring
mkdir -p snap hits
while true; do
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  rm -f snap/*.jpg
  ls -t "$RING" | awk 'NR%90==1' | head -5 | while read f; do cp "$RING/$f" snap/ 2>/dev/null; done
  for img in snap/*.jpg; do
    [ -f "$img" ] || continue
    hit=0
    for pm in 1340:champion 1341:runF 1342:runH 1343:runG; do
      port=${pm%%:*}; model=${pm#*:}
      t0=$(date +%s%N)
      out=$(curl -s -m 10 -F "file=@$img" "http://127.0.0.1:$port/api/image")
      ms=$(( ($(date +%s%N) - t0) / 1000000 ))
      boxes=$(echo "$out" | jq -c '[.result.bounding_boxes[]? | {l:.label, v:(.value*1000|round/1000), x, y, w:.width, h:.height}]' 2>/dev/null)
      [ -n "$boxes" ] || boxes='"ERR"'
      echo "{\"ts\":\"$ts\",\"frame\":\"$(basename "$img")\",\"model\":\"$model\",\"ms\":$ms,\"boxes\":$boxes}" >> live.jsonl
      [ "$boxes" != "[]" ] && hit=1
    done
    [ $hit = 1 ] && cp "$img" hits/
  done
  sleep 60
done
