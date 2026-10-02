"""Score the night-tone A/B set against a running Edge Impulse HTTP runner.

Runs on the board. For every frame in <dir>/orig and <dir>/tone it posts the
image to the runner and appends one JSON line per frame and variant:
{"frame", "variant", "boxes": [{"l", "v"}]}. Stdlib only (the board host has
no requests/PIL guarantee).

Usage: python3 score_night_tone.py <dir> <out.jsonl> [port]
"""

import json
import os
import sys
import urllib.request
import uuid


def post_image(port, path):
    """POST one JPEG to the EI runner on `port` and return its JSON reply."""
    boundary = uuid.uuid4().hex
    with open(path, "rb") as fh:
        payload = fh.read()
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"{os.path.basename(path)}\"\r\nContent-Type: image/jpeg\r\n\r\n"
    ).encode() + payload + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/image",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def main():
    """Score every frame under root into out_path, skipping ones already done."""
    root, out_path = sys.argv[1:3]
    port = int(sys.argv[3]) if len(sys.argv) > 3 else 1337
    done = set()
    if os.path.exists(out_path):
        with open(out_path) as fh:
            for line in fh:
                row = json.loads(line)
                done.add((row["frame"], row["variant"]))
    with open(out_path, "a") as out:
        for variant in ("orig", "tone"):
            folder = os.path.join(root, variant)
            for name in sorted(os.listdir(folder)):
                if (name, variant) in done:
                    continue
                result = post_image(port, os.path.join(folder, name))
                boxes = [
                    {"l": b["label"], "v": round(b["value"], 4)}
                    for b in result["result"].get("bounding_boxes", [])
                ]
                out.write(json.dumps({"frame": name, "variant": variant, "boxes": boxes}) + "\n")
                out.flush()


if __name__ == "__main__":
    main()
