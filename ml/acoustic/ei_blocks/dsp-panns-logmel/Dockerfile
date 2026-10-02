FROM python:3.11-slim-bookworm

WORKDIR /app

# libsndfile is librosa's audio backend and is not in the slim image. The
# soundfile wheel links against it at import time, so a missing libsndfile
# surfaces as an ImportError on the first request rather than at build time.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libsndfile1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY parameters.json dsp.py dsp-server.py ./

# Warm the numba caches librosa builds on first call. Without this the first
# window the Studio sends takes tens of seconds to JIT, which reads as a hung
# block rather than a cold start.
#
# Deliberately 8 kHz in, not 32 kHz. 32 kHz is the rate the filterbank is
# defined at, so passing it here skips the resample branch entirely - and
# that branch runs on every real window, because the impulse is 8 kHz. A
# warm-up that misses it leaves soxr's own JIT cold and exercises none of
# the path that ships. 8000 samples is one second, which is all the cache
# warming needs.
RUN python -c "import dsp, numpy as np; dsp.generate_features(1, False, np.zeros(8000, dtype=np.float32), ['audio'], 8000)"

EXPOSE 4446
ENTRYPOINT ["python", "-u", "dsp-server.py"]
