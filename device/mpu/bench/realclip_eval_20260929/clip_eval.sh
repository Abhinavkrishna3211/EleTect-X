#!/bin/sh
# Run every extracted encounter-clip frame through each model's runner (ports 1340-1343)
# and append all boxes >= 0.05 to clips.jsonl. Frame names are <category>__<clip>__<n>.jpg.
cd "$(dirname "$0")"
for img in frames/*.jpg; do
  for pm in 1340:champion 1341:runF 1342:runH 1343:runG; do
    port=${pm%%:*}; model=${pm#*:}
    out=$(curl -s -m 10 -F "file=@$img" "http://127.0.0.1:$port/api/image")
    boxes=$(echo "$out" | jq -c '[.result.bounding_boxes[]? | {l:.label, v:(.value*1000|round/1000)}]' 2>/dev/null)
    [ -n "$boxes" ] || boxes='"ERR"'
    echo "{\"frame\":\"$(basename "$img")\",\"model\":\"$model\",\"boxes\":$boxes}" >> clips.jsonl
  done
done
echo CLIPS DONE >> clip_eval.out
