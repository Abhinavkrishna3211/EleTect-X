# Acoustic evaluation harness

Off-device evaluation for the four-class acoustic model (`gunshot`, `chainsaw`, `elephant_call`,
`ambient`). It exists to answer two questions the Edge Impulse project could not:

1. **What is the held-out accuracy when the split is honest?** Every number in
   `ml/acoustic/README.md` was measured on a file-level split of a corpus that contains many
   near-duplicates of each source recording, so those numbers are optimistic by an unknown and
   per-class-uneven margin.
2. **Is ~58% a task ceiling or a from-scratch-training ceiling?** The README closed architecture
   search with "data ceiling, not capacity ceiling" after two small nets tied. That is sound for
   training from scratch on this much data; it is not evidence the task itself is capped.

## The split rule

Split on the **source recording**, never the file. See
`docs/decisions/0025-acoustic-recording-level-split-integrity.md` for the three leaks this
found and fixed. In short, one recording's group covers all its windows and gain variants; ESC-50
keys on the Freesound id it embeds; AudioSet/VGGSound key on the YouTube video id; and a trailing
`.<n>` on a field capture is a chunk index, so a session moves as one unit.

`freeze_split.py` prints the count of recordings appearing on both sides and fails if it is
non-zero. Feature caches are re-keyed against the frozen split by filename at load time, so a
cache that predates a re-freeze is an error rather than a silently wrong test set.

## Reading the numbers

- Per-class recall carries a **95% bootstrap CI** over resampled test recordings. Seed spread is
  not the uncertainty measure: a deterministic head scores identically across seeds and would
  report zero uncertainty for a 68-recording class.
- The **field slice is small** — 39 ambient, 30 elephant_call, 2 chainsaw, 1 gunshot recordings.
  Per-class field accuracy is not reportable for chainsaw or gunshot. More field *sessions* (not
  more minutes in one session) is the highest-value data work available.
- Precision matters as much as recall here. A chainsaw alert dispatches a forest officer, so a
  false positive has a real cost borne by the people being asked to trust the system.

## Pipeline

```bash
# 1. index every clip, resolving each to its source recording
python ml/acoustic/harness/build_index.py                      # add --audioset to include AudioSet

# 2. freeze a group-aware split (asserts no recording straddles the boundary)
python ml/acoustic/harness/freeze_split.py

# 3. reproduce the deployed MFE + small-CNN recipe on that split - the control
python ml/acoustic/harness/baseline_mfe.py

# 4. embed with an AudioSet-pretrained PANNs backbone, then fit a head
python ml/acoustic/harness/embed.py --arch cnn14 --resume      # cnn6 is the deployable size
python ml/acoustic/harness/train_head.py --emb embeddings_cnn14.npz --head mlp --seeds 5 --balanced

# 5. name the false positives and sweep the decision threshold
python ml/acoustic/harness/error_audit.py --target chainsaw --floor 0.85
```

Run these from the repository root: `split.json` stores repo-relative audio paths.

To add a corpus to training without disturbing the benchmark, use `augment_split.py`, which writes
a new split only if the test set is unchanged:

```bash
python ml/acoustic/harness/build_index.py --audioset --out ml/acoustic/harness/index_as.json
python ml/acoustic/harness/augment_split.py --index ml/acoustic/harness/index_as.json --source audioset
```

## Files

| file | role |
|---|---|
| `build_index.py` | resolve every clip to a source recording; the split rule lives here |
| `freeze_split.py` | write a group-aware split and assert it is clean |
| `augment_split.py` | add a corpus to train only, refusing to touch the test set |
| `baseline_mfe.py` | the deployed MFE + `conv1d(16)->conv1d(32)->dense(24)` recipe, as the control |
| `panns_small.py` | Cnn6/Cnn10, vendored verbatim from `qiuqiangkong/audioset_tagging_cnn` (MIT) |
| `embed.py` | extract PANNs embeddings; `--resume` keeps what a previous run computed |
| `train_head.py` | fit logreg/MLP heads, report per-class recall, precision and bootstrap CIs |
| `error_audit.py` | list the false positives by name and sweep per-class thresholds |

`panns_small.py` is byte-for-byte upstream because the released checkpoints only load into that
exact architecture; lint is disabled for that file alone.

Generated artefacts (`*.npz`, `index.json`, `*.log`) are git-ignored. `split.json` is **not**:
the frozen split is what makes two runs comparable, so it is committed deliberately.
