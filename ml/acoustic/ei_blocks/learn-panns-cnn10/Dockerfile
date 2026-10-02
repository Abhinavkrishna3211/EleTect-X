FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
# CPU wheels only. The backbone is frozen and the head is two linear layers over
# 512 floats, so training is embedding-bound, not gradient-bound - a CUDA build
# would add gigabytes to the image for no measurable speedup.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
        torch==2.4.1 \
    && pip install --no-cache-dir -r requirements.txt

# Bake the AudioSet checkpoint in rather than fetching it per training run: the
# run then does not depend on Zenodo being reachable, and every run provably
# uses the same weights.
ENV PANNS_CKPT_DIR=/app/panns_data
RUN mkdir -p $PANNS_CKPT_DIR \
    && curl -fsSL -o "$PANNS_CKPT_DIR/Cnn10_mAP=0.380.pth" \
        "https://zenodo.org/record/3960586/files/Cnn10_mAP%3D0.380.pth?download=1" \
    && curl -fsSL -o "$PANNS_CKPT_DIR/Cnn6_mAP=0.343.pth" \
        "https://zenodo.org/record/3960586/files/Cnn6_mAP%3D0.343.pth?download=1"

COPY panns_small.py train.py parameters.json ./

ENTRYPOINT ["python3", "-u", "train.py"]
