"""Upload real, CC BY 4.0 Roboflow wildlife datasets to Edge Impulse as FOMO training data.

Pulls openly-licensed, bounding-box-annotated datasets straight from Roboflow's
export API, converts their COCO annotations into Edge Impulse's bounding_boxes.labels
ingestion format, and uploads them into the EleTect-X-Vision project:

  - "Elephant": roboflow-universe-projects/elephant-detection-cxnt1, version 2
    ("resized640"), CC BY 4.0. 3,280 images / 4,478 boxes, 640x640.
    Version 2 is used rather than version 4 deliberately: v4 holds the same 3,280
    source images plus a 5x Roboflow augmentation of the train split only (12,460
    total). Those extra frames carry no new information, would put the class ratio
    against boar at 6.6:1 instead of 1.7:1, and Edge Impulse applies its own
    augmentation during FOMO training regardless. v2 is the un-augmented base set.
  - "Boar": trackabox-4ejy9/wild-boar-a1flm, version 1, CC BY 4.0.
    1,901 images / 2,739 boxes, 416x416. Roboflow labels this class "Pig"; the
    dataset is titled "Wild Boar" and its filenames are wild-boar frame captures
    (wb_frames...), so the class is relabeled to "Boar" here rather than carrying
    the misleading name into this project. The project also carries a stray,
    zero-annotation category literally named "`" - it is dropped, and counted.
  - "Boar" (top-up): boarwatch/wild-boar-deterrent-pzq5t, version 1, CC BY 4.0.
    8,857 images / 13,894 boxes, 416x416, class "0" renamed to "Boar". Added to close
    the instance gap against Elephant (stock FOMO knobs - resolution, cycles, class
    weighting, augmentation - are exhausted; see ml/vision/README.md's iteration
    log). A byte-identical fork of this same 8,857-image dataset is also listed as
    deepanshu-thapa-bgz3j/wild-boar-deterrent; only the boarwatch listing is used,
    so the same photos are never counted twice under two names.
    Its filenames collapse to only 2,483 real groups behind the 8,857 images (most
    of the "extra" images are re-exports of the same source photo at a second
    resolution, not new content) - see SAMPLE_SEED below. group_key()'s frame-tail
    stripping (built for Trackabox's genuine wb_framesNNNNN video-frame sequences)
    over-merges this set's catalog-style sequential IDs (Wild_Boar_0001,
    Wild_Boar_0002, ... are DIFFERENT source photos, not consecutive video frames -
    confirmed by checking date_captured, which is flat upload-time metadata, not a
    real capture timestamp, so it cannot distinguish the two cases; distinguished
    instead by the exact-stem duplicate-group size topping out at 6, versus the
    1,155-image mega-group frame-tail stripping produces when wrongly applied here).
    group_key_exact() is used for this source instead: only Roboflow's own
    "_jpg.rf.<hash>" rewrite is stripped, so same-photo re-exports still collapse
    into one group but distinct sequentially-numbered photos do not.
    Only ~1,379 of the 2,483 groups are sampled (one representative image per
    group, group order shuffled under SAMPLE_SEED) - enough to bring Boar's total
    from 1,901 to 3,280, exactly matching Elephant, without pulling in either
    redundant re-exports of the same photo or more images than Elephant has.

552 of the 3,280 elephant images and 4 of the 1,901 trackabox boar images carry no
bounding box at all. Those are not defects and are not discarded: the elephant set
ships deliberate non-animal scenes (casino, hospital-corridor, Kindergarden_classroom,
pantry, Libreria) as hard negatives. They are uploaded with an empty boundingBoxes
list, which is how Edge Impulse marks a background sample, so FOMO learns what "no
animal" looks like instead of only ever seeing frames that contain one.

Both datasets are general daytime/colour wildlife photography. Neither is
IR-illuminated night camera-trap footage, while ADR 0001
(docs/decisions/0001-usb-camera-imx462.md) puts >70% of elephant raids at night
behind 940nm active IR. This script closes "a two-class FOMO model is trained on
real, licensed data" - it does not establish anything about night field
performance. See ml/vision/README.md for the full caveat list.

The split is group-aware, not per-image. Both sets mix standalone photos with
runs of consecutive video frames (elephant "E026-..." x155, "casino-..." x103;
boar "Wild_Boar-..." x306, "wb_framesa00001-..." x254), and Roboflow gives the
boar set no test split at all (train 1,901, valid 0, test 0). A naive per-image
80/20 would put near-identical adjacent frames on both sides and inflate the
held-out number. Images are grouped by source-clip stem and whole groups are
assigned to one side - the same "split by event, not by sample" discipline
scripts/edge_impulse_upload_seismic.py already uses. The assignment is seeded
and written to ml/vision/dataset_manifest.json so the split behind the reported
number is reproducible from a fresh clone.

Usage (run from a machine with normal internet access, not a sandboxed one):

    set EI_API_KEY=ei_...
    set EI_PROJECT_ID=1097972
    set RF_API_KEY=...
    python scripts\\edge_impulse_upload_vision.py

    python scripts\\edge_impulse_upload_vision.py --dry-run --limit 20

Downloaded zips and extracted images land in ml/datasets/vision/raw/, which is
already gitignored (.gitignore covers ml/datasets/**/*.zip and ml/datasets/**/raw/),
so ~300MB of source imagery never enters the repo.

Requires only the standard library - no pip install needed.
"""

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

INGEST = "https://ingestion.edgeimpulse.com/api"
STUDIO = "https://studio.edgeimpulse.com/v1/api"
ROBOFLOW = "https://api.roboflow.com"

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
CACHE_DIR = os.path.join(_ROOT, "ml", "datasets", "vision", "raw")
MANIFEST = os.path.join(_ROOT, "ml", "vision", "dataset_manifest.json")

# Fixed so the split is reproducible; recorded in the manifest and the README. Also
# reused to shuffle group order when a source declares sample_target (BoarWatch).
SPLIT_SEED = 20260822

# A box below this fraction of the image's area is treated as a degenerate/defective
# annotation, not a real small-and-distant animal. Threshold set from a 29 Aug visual
# audit of every box the full-corpus geometry scan flagged below this line (8 boxes
# across 4 sources: swg-eurasian-wild-pig, elephant-detection-cxnt1-v2,
# wcs-sus-scrofa, pseudo-ir-elephant) - 8/8 were confirmed by eye to be bad, not just
# small: three were single-digit-pixel slivers sitting on bare forest floor with no
# animal visible anywhere in a wide crop around them; the other five sat on real,
# clearly visible animals (an elephant herd, a boar) but landed on empty road/ground
# between legs or beside the body, not on the animal itself - never a tight box around
# a genuinely tiny distant subject. In every multi-box image checked, the degenerate
# box was one spurious extra alongside otherwise-normal boxes for the same animals, so
# dropping it costs nothing; where it was the image's only box, the image correctly
# reverts to a background sample, which is the right outcome for a box that was never
# actually anchored to anything. 0.0003 (0.03% of frame area) is the exact cutoff the
# audit used - every box below it failed, and nothing between 0.0003 and the next
# extreme-area bucket up was sampled, so do not lower this further without a fresh
# visual check.
MIN_BOX_AREA_FRACTION = 0.0003
TEST_FRACTION = 0.20
# A group is only allowed into the test side if it still fits this far over target,
# so one 306-image clip cannot drag the held-out share far past 20%.
TEST_OVERSHOOT = 1.10
# Edge Impulse caps a files request at 1000 files / 100MB per file. 64 keeps each
# request well under any request-size limit while still being ~80 requests total.
BATCH_SIZE = 64
MAX_RETRIES = 4

# Manual visual audit, 28 Aug (n=56 across the two contaminated Boar sources: 40 from
# wild-boar-a1flm-v1, 16 from wild-boar-deterrent-pzq5t-v1, random seed 20260828).
# Every filename below was individually opened and read - not a heuristic flag - and
# is one of: a different suid species entirely (red river hog, warthog), a
# domestic/farm pig (floppy ears, ear tags, farm pens, straw bedding, spray-paint
# livestock marks), or a domestic breed with a wild-boar-incompatible coat (woolly
# Mangalitsa-type). This is a spot-check exclusion, not a full relabel - the true
# contamination rate in each source's full pool (1,897 / ~6,200 boxed images) is
# almost certainly higher than what n=56 alone can catch. A full manual pass over
# every image remains the only way to certify this data clean; that has not been done.
#
# 29 Aug - the seed-20260828 sample above was drawn at n=60/source (120 total) but
# only 56 of those 120 were actually opened by eye in the 28 Aug pass; the remaining
# 64 (20 from wild-boar-a1flm-v1, 44 from wild-boar-deterrent-pzq5t-v1) are closed out
# here rather than left as an unreviewed tail of an already-prepared sample. Same
# "domestic-pig contamination heuristic" task named in the standing plan: there is no
# reliable filename signal (both sources use the same Roboflow auto-hash naming as the
# elephant bare-numeric bucket), so this stays a full visual open-and-read pass, not a
# pattern rule. 17 more confirmed contaminated, three new sub-categories beyond the 28
# Aug list's three: hunting-trophy photography (human posed with the animal, same
# "human present, posed" precedent already in the 20260822 second-pass list below, now
# named explicitly), zoo/wildlife-park enclosures (fencing, buildings, other captive
# species in frame - the same domain-concern standard just applied to Elephant's
# captive/managed-care bucket), and one apparent taxidermy mount / statue (noted with
# its own lower-confidence caveat rather than asserted flatly). One entry
# (0241257f22543c1a) looked like cattle at contact-sheet thumbnail resolution and was
# re-opened at full size before being filed - it is a spotted piebald domestic pig
# pair, not cattle; worth naming as a reminder that a thumbnail call gets a full-res
# check before it's trusted. Combined with the 28 Aug + 20260822 passes, this closes
# out the full 120-image seed-20260828 sample and brings the running total to 144
# distinct images opened by eye across both sources (120 + the separate 24-image
# seed-20260822 sample), 40 confirmed contaminated (~28%). Still not a
# full-population certification - 144 of ~10,758 total images in the two sources -
# see this constant's own running caveat above; that full pass remains undone and is
# not planned given the size (roughly 75x the elephant bare-numeric bucket that did
# get a full pass 29 Aug).
BOAR_VISUALLY_CONTAMINATED_FILENAMES = {
    # wild-boar-a1flm-v1
    "d7154f3779821de9_jpg.rf.1d06037a219971872ea97772dd37215b.jpg",  # red river hog
    "1IAYSQYFEA8Q_jpg.rf.b9bf0a5d5efd5babde44b78b17ac8c63.jpg",  # domestic pig, pasture
    "5G43741K8NPY_jpg.rf.43d6f724201912de30fd7b8d0a2b6961.jpg",  # domestic pig, straw
    "d7c11e86dd8ffd38_jpg.rf.e741bcc33088655b9f26b660a3b58156.jpg",  # domestic pig, woodchip pen
    "AKBYJRHQCL5J_jpg.rf.db49f8499f1e12b2e71f40c6971120f1.jpg",  # domestic pig, farm pen
    "9965b39bd2656ca1_jpg.rf.8cd037d8aa09de93bcd6f662e88fc681.jpg",  # domestic pig, livestock mark
    "RY1FXEUNVGYF_jpg.rf.bdcfc932a1ef5adc181d4b8c13d117c3.jpg",  # woolly domestic breed
    "ZZ2S3FNL3X4B_jpg.rf.88bdfd02fc4efb6e5ab728676bb88355.jpg",  # farm shelter, likely domestic
    "0BG9FX1AKE79_jpg.rf.bde8aac5952fa41a6d1c1da7fce7169a.jpg",  # black piglet litter, likely domestic
    # wild-boar-deterrent-pzq5t-v1
    "GIJCZQVE6KUK_jpg.rf.68cb6c38ca7dc3a111f4d1a855a23449.jpg",  # warthog
    "512PQCA13JE7_jpg.rf.f8a91269b9cc13f94d5df6bee60daeb3.jpg",  # warthog, captive
    "WFH57W23NPDJ_jpg.rf.54885b40b28242f465394e293655d47f.jpg",  # domestic pig, ear tag
    # 28 Aug "verify all our datasets" pass, second Boar sample (n=24: 12 from
    # wild-boar-a1flm-v1, 12 from wild-boar-deterrent-pzq5t-v1, seed 20260822) -
    # same manual-open discipline as the n=56 pass above, confirming its own
    # caveat that the true rate is higher than any one sample catches. 11/24 new
    # confirmed contaminated, filenames durably tracked via a manifest so the
    # finding survives context loss (see scratchpad audit tooling, not checked
    # into this repo). wild-boar-a1flm-v1:
    "R5UPLY6VTJPF_jpg.rf.ff438f86ed7d5714f871993dd41b030a.jpg",  # domestic pig, barn corner
    "NBFN4ALN7RZ5_jpg.rf.f6f4529440f76572668d066a576911ba.jpg",  # captive/fenced enclosure
    "MSKWMCT25JS5_jpg.rf.4710a4a114c6f48a7bfa894795eba09b.jpg",  # watermarked stock (Jurgen Schiersmann)
    "1BHJZ8RPXZ30_jpg.rf.164a8116f6caca1f7610882ed75afe5b.jpg",  # watermarked stock
    # wild-boar-deterrent-pzq5t-v1
    "MSKWMCT25JS5_jpg.rf.bd373942eb9b7414a45a0717f93db02a.jpg",  # same Schiersmann photo, re-exported
    "594de6e1715daf41_jpg.rf.bcfc6544107c1888b6460a8b1f691c10.jpg",  # captive/indoor, overexposed porch
    "12d8f8f5d3f21651_jpg.rf.39f1d0854c6b05ef1681bcef9d7d7af7.jpg",  # human present, posed roadside photo
    "CH2YPA1NQ34C_jpg.rf.8184b0331d72eb2f55253222f8ff981d.jpg",  # captive/fenced pen
    "H663VBVK9P9B_jpg.rf.1044317da827f95cd893b80c0776f7fc.jpg",  # watermarked stock (parisch-naturfoto.de)
    "cf3b260202064e36_jpg.rf.eea81a5c040e09a4630dc4344b305d0f.jpg",  # captive pig pen, chain-link + doghouse
    "CQN7OAKVMDJY_jpg.rf.519edfd59be63cc79f3fd4369076d243.jpg",  # wrong species, warthog
    # 29 Aug, remainder of the seed-20260828 n=120 sample (see comment above) -
    # wild-boar-a1flm-v1:
    "5XES1A8VS4L8_jpg.rf.7d909e900ef380e4fbce3ad9ee9294ce.jpg",  # smooth reddish-tan coat, domestic-breed coloring
    "J0GGGUCGG6OI_jpg.rf.0793c54842ee3c1d016067a4d7101a5f.jpg",  # large floppy forward ears, domestic-breed indicator
    "IP8ZBT7MTJEG_jpg.rf.e90d09ddbf2c1361a2f551ab70995263.jpg",  # piglet on a rope leash/tether, captive/pet
    "13737d6d8c12177f_jpg.rf.498a5b6661cf16ba967fa76dd0c336fa.jpg",  # sow nursing piglets, wooden farm pen + straw
    "6A4K9115HKFW_jpg.rf.adfe6130fe0bba426dfccb698904f3cb.jpg",  # resting on a raised wooden pallet/platform, managed enclosure
    "c7fdeec595a38850_jpg.rf.b187fe8b60353c2c8016325192a9a55e.jpg",  # piglets nursing on straw, domestic husbandry
    "cd57f105f9b8bdbf_jpg.rf.dd7007d51170b66aba619186431f98da.jpg",  # spotted black/tan/white coat, domestic-breed pattern
    # wild-boar-deterrent-pzq5t-v1
    "0IYOAUWDTUYW_jpg.rf.ab24f30362c316c016ca7a3524cfb17b.jpg",  # warthog - facial warts, upward-curving tusks
    "YVF4JW8WCA8P_jpg.rf.486aa9cd17bd119312fcb44896112982.jpg",  # hunter posed with the animal, trophy photograph
    "U9238TLIL4C3_jpg.rf.8223c568f8b1068197c332c2c1e403df.jpg",  # smooth reddish-tan coat, domestic-breed coloring
    "548fb47bcfb9b95f_jpg.rf.0f0364c5155fe69750ab50b68102531b.jpg",  # spotted domestic pig with nursing piglets, straw stall
    "O4958MKPPPRR_jpg.rf.48c2e495f556f400ce7391e39282d367.jpg",  # zoo mixed-species enclosure, fencing + buildings
    "SBMYEGA2HUO4_jpg.rf.8b160698d2be4cea45a0758bb4002b63.jpg",  # hunter posed with the animal, trophy photograph
    "KEE7C8UWMD2I_jpg.rf.e50146d620dfad0c442cf603f695684d.jpg",  # human hand directly hand-feeding at close range, tame
    "IOMYRKHXZ1B7_jpg.rf.b7d3e49ab86590eaeddbbc0ca119d8c5.jpg",  # zoo/wildlife-park mixed-species enclosure
    "535VHNHXLVJW_jpg.rf.8f927e3253cc8ae1ef50db93495a5a3f.jpg",  # apparent taxidermy mount/statue, not a live animal (lower confidence)
    "0241257f22543c1a_jpg.rf.a96dbe3ecf15178b0bb92803e8e89561.jpg",  # spotted piebald domestic pigs, farmyard street scene (verified at full res, not just the thumbnail)
}

# 29 Aug data-quality re-verification: the same bare-numeric-filename audit that
# found the nine African elephants folded into AFRICAN_ELEPHANT_VISUALLY_CONFIRMED_
# FILENAMES above also turned up contamination that is not a species mismatch -
# same discipline as BOAR_VISUALLY_CONTAMINATED_FILENAMES, one explicit
# visually-audited list per defect type found in this pass, not a heuristic:
#   - not an elephant at all: four frames from what looks like a mis-scraped
#     pandemic/news batch - people wearing face masks on transit, in a crowd, at
#     an airport arrivals hall. Wrong subject entirely, not a boxing or species
#     defect.
#   - wrong domain, non-photographic or non-field: a sepia Victorian-era photo of
#     a mahout-led elephant with people in top hats on a cobblestone street, and
#     three studio/e-commerce cutout shots on a flat white background. Real
#     elephants, but neither is remotely representative of camera-trap field
#     imagery, and training on a white studio backdrop risks teaching the
#     detector that background matters to the label.
#   - watermarked stock photography (Getty, iStock, Shutterstock, Alamy, BigStock,
#     Minden Pictures, pixtastock, africanimagelibrary.com): same defect this file
#     already excludes for Boar (see BOAR_VISUALLY_CONTAMINATED_FILENAMES) - a
#     visible watermark is baked into the pixels the model would learn from.
#   - captive/managed-care domain (zoo enclosure fencing or bars, chain-link,
#     hay bedding, a chain or rope on the animal, a bathing trough, a zoo logo or
#     visible spectator crowd, a caparisoned/ceremonial temple elephant): real
#     Asian elephant, correctly boxed, but not field/camera-trap habitat. The 28
#     Aug note on _is_named_african_elephant() deliberately left one single
#     captive frame (as_tr14) unfiltered, calling it "a domain concern worth a
#     future pass, not excluded here" because one anecdote did not justify a
#     policy. This is that future pass: a full 142-image audit found 25 more
#     captive-domain frames in this one bucket alone, which is enough evidence to
#     act on, not just note.
ELEPHANT_VISUALLY_CONTAMINATED_FILENAMES = {
    # not an elephant at all
    "012106_jpg_1140x855_jpg.rf.40ac7554df9e1173c0433c2c84f08582.jpg",  # masked person, transit
    "1482202839575_jpg.rf.097b29db6806f73d07a0b1b9e5f3f933.jpg",  # masked crowd, street
    "1579924271_jpg.rf.4e9f1e0a4e6640034fff49d01bc40cfe.jpg",  # masked crowd
    "1580128422_jpg.rf.db74eb769303b68cde387d521c5912f6.jpg",  # masked crowd, airport arrivals hall
    # wrong domain: historical / studio backdrop, not field photography
    "5_jpg.rf.f8bbc57d667f15a508833080bebf9a0f.jpg",  # sepia historical photo, mahout + people in top hats
    "64_jpg.rf.c41a057a3ae20d193527ad799b1943ba.jpg",  # studio cutout, flat white background
    "65_jpg.rf.5cf3dccbdd44b69a310a301148637c40.jpg",  # studio cutout, flat white background
    "70_jpg.rf.072d8a991ccade8d5d31303b9b1bb20d.jpg",  # studio cutout, flat white background
    # watermarked stock photography
    "00545094_jpg.rf.4fc5d4054920622cfc79868027323a90.jpg",  # Minden Pictures watermark
    "104166947_jpg.rf.e982ddeb8c225c463c0dfba82398f786.jpg",  # BigStock watermark
    "19_jpg.rf.9ede484ba0e950c8d93dd78fea124dce.jpg",  # BigStock watermark
    "1_jpg.rf.34316d7406ea90150e266e7dc9448746.jpg",  # iStock watermark
    "27_jpg.rf.0b71fdc90d1cebd35b5dade22e127f8d.jpg",  # Shutterstock watermark, chained calf
    "28_jpg.rf.fbeebdced6eca33e880a1f9150faa6bb.jpg",  # Getty Images watermark
    "29_jpg.rf.0a2ff617fd369df91d296cf0a55c0926.jpg",  # Shutterstock watermark (ID 548075806)
    "29_jpg.rf.7e2fcfcb5ba9fc59b41be55cf706e04b.jpg",  # Getty Images watermark
    "2_jpg.rf.79a0740531ecfbd48ec5a7b2aed5d48b.jpg",  # Getty Images watermark
    "30_jpg.rf.3a5b07b7b0c43926d6fb0edbba53fabd.jpg",  # Getty Images watermark
    "31_jpg.rf.48d98f118866655dd91238010ebe9968.jpg",  # Alamy watermark
    "38_jpg.rf.0eaaf18990aa8659275e26e434c18301.jpg",  # iStock watermark, rope on animal
    "45_jpg.rf.60302b9b63c8f8ce8228abc6cc152c07.jpg",  # Alamy watermark
    "46_jpg.rf.61037c49627ae793e409b129b1285a35.jpg",  # Shutterstock/ActiveWild.com watermark
    "4_jpg.rf.f468b93771046edc11f2b81329b67154.jpg",  # iStock watermark
    "57_jpg.rf.3ca6f5f451e6b6f75803b9ba751c08fa.jpg",  # Alamy watermark
    "67915702_jpg.rf.6775e309afb08fc43fa6ef78a56ce7b8.jpg",  # pixtastock.com watermark
    "7_jpg.rf.c7774e76e80cbf408142406981d0b19e.jpg",  # iStock watermark
    "90923798_jpg.rf.1242b72826608db7d6360a175f4e8f40.jpg",  # BigStock watermark
    # captive / managed-care domain
    "17_jpg.rf.95f02248c93fba81545ddfc10bf91522.jpg",  # wooden fence, enclosure
    "18_jpg.rf.af015b0c0726a3fb9268d3fef06924eb.jpg",  # zoo enclosure
    "20_jpg.rf.2e0ca6b5e9bf861e310489c4d79d2b6d.jpg",  # sanctuary/orphanage doorway
    "23_jpg.rf.c706621bd429461187ad8666137132df.jpg",  # hay bedding, resting pair
    "25_jpg.rf.e86d6521c08222035f839aa33c757c7f.jpg",  # zoo rock enclosure
    "28_jpg.rf.48b9dc5a94cfb339c3a1c0f44ed60e74.jpg",  # hay bedding, managed care
    "32_jpg.rf.77ed730ff4335e5731345e72bbd00c36.jpg",  # zoo, paved ground
    "36_jpg.rf.baabed28c80229bfc9ed10d19d47c7f7.jpg",  # zoo rock enclosure
    "41_jpg.rf.3569724b9c1e34ec5edb183a8c65a19d.jpg",  # zoo enclosure prop (dead tree, rocks)
    "42_jpg.rf.c3789ca56bfa0038d62cc68fdafa768f.jpg",  # chain-link fence visible
    "43_jpg.rf.ebe02e75aaba26dfa4efc109b67c5e93.jpg",  # zoo cage bars in foreground
    "43_jpg.rf.f63ec7ad8557105c5dcf7c31e244e45f.jpg",  # fence visible
    "44_jpg.rf.3793b6de1089a4da0bcde6634fbdd256.jpg",  # wooden stall structure
    "44_jpg.rf.6ec4bb5335cda5a93ff20cf2eef72fa9.jpg",  # fence visible
    "45_jpg.rf.12ff783e1f058f5b3aafb8be41899382.jpg",  # zoo logo visible in frame
    "48_jpg.rf.7373356cf4a8ac6d2b5f62cdfe3524d6.jpg",  # zoo backdrop, spectators visible
    "53_jpg.rf.e4de7245f16865113758cf6884f5d25a.jpg",  # captive sandy enclosure
    "54_jpg.rf.6856874f6ada272eab7dae5ce17c56c2.jpg",  # themed zoo enclosure, artificial waterfall
    "5_jpg.rf.6ea654cb89624c83c65e251e8ebc2d77.jpg",  # chain visible on leg
    "63_jpg.rf.341e8244ada257ba241ba24328d6269e.jpg",  # wooden fence enclosure
    "68_jpg.rf.94b565c3951f63d8758088e11d818b4c.jpg",  # garden fountain, park setting
    "75_jpg.rf.10a9a585eeb1ab0a0272ddeec0b29172.jpg",  # zoo/sanctuary enclosure, stone wall
    "8_jpg.rf.a60204e44cac029bf3e2a47fe214c4d5.jpg",  # calf being bathed in a trough
    "4_jpg.rf.7e09e2bba3406fc12d61efce6707ff78.jpg",  # captive enclosure, mowed grass + pavement
    "49_jpg.rf.1809f1e71f73704c09540c8500b9c480.jpg",  # caparisoned ceremonial temple elephant
}

DATASETS = [
    {
        "label": "Elephant",
        "workspace": "roboflow-universe-projects",
        "project": "elephant-detection-cxnt1",
        "version": 2,
        "slug": "elephant-detection-cxnt1-v2",
        "license": "CC BY 4.0",
        "expect_images": 3280,
        # Cross-check only. The Roboflow project page reports 4,478 boxes; the frozen
        # v2 export actually carries 4,477 (432 test + 3,166 train + 879 valid). The
        # export is what gets uploaded, so the export is what the README reports.
        "page_boxes": 4478,
        "rename": {},
        "drop": set(),
        # 27 Aug 3a species-verification finding (ml/vision/README.md): this source
        # is contaminated with African bush elephant (a different species from the
        # Kerala deployment's Asian elephant target). A full-population filename
        # scan found 34 images (1.0%) explicitly naming an African range
        # country/park - a documented floor, not the true rate (a 23-image visual
        # sample read ~17% African). Filtering these 34 is the cheap half of that
        # finding's recommendation; the species-correct supplements below
        # (asian-elephants-dataset-v1, thai-elephant-dataset-v6) are the structural
        # half.
        "filter_out_of_species": True,
        # 28 Aug data-quality re-verification: see AFRICAN_ELEPHANT_VISUALLY_CONFIRMED_FILENAMES
        # and TV_BROADCAST_CLIP_PREFIXES above for what these two flags actually filter and why.
        "exclude_broadcast_clips": True,
        # 28 Aug data-quality re-verification, third pass: see
        # _is_generic_named_scrape's docstring above - 16/16 sampled "Image<N>_"/
        # "images<N>_" filenames in this source were not real Asian-elephant field
        # photography (TV broadcast, stock photography, or African elephant).
        "exclude_generic_named_scrape": True,
        # 29 Aug data-quality re-verification: see ELEPHANT_VISUALLY_CONTAMINATED_FILENAMES
        # above for what this filters and why (not-an-elephant, historical/studio,
        # watermarked stock, captive/managed-care domain).
        "exclude_filenames": ELEPHANT_VISUALLY_CONTAMINATED_FILENAMES,
        # 28 Aug data-quality re-verification, frame-clip audit: this source's
        # single largest clip ("frame4338"-"frame5791", 984 images, ~39% of the
        # whole source) is one continuous dashcam sequence of a real elephant -
        # the viral RAJAMURUGAN "elephant reaching into a stopped truck" video,
        # baked-in "U TURN" overlay text (a known, documented artifact, not
        # filtered - the elephant and box are real). Confirmed by an evenly-
        # spread 10-frame contact sheet across the whole numeric range: same
        # truck-and-elephant scene start to finish, genuinely one clip. User
        # decision on this finding: keep as legitimate training data but cut its
        # duplication down to a handful of diverse representative frames - see
        # cap_named_group()'s docstring for the mechanism.
        "group_caps": {"frame": 10},
    },
    {
        "label": "Elephant",
        "workspace": "customdataset-aucsj",
        "project": "asian-elephants-dataset",
        "version": 1,
        "slug": "asian-elephants-dataset-v1",
        "license": "CC BY 4.0",
        # 3a species check found real African-elephant contamination in the original
        # 3,280-image class (34/3,280 by filename, ~17% on a 23-image visual sample;
        # see ml/vision/README.md) - this dataset is species-correct by construction,
        # not a spot-check fix, and is the structural half of that finding's
        # recommendation (filter_out_of_species above is the cheap half). Only version
        # that exists for this project. Roboflow's own generation step 3x-augments (flip/rotate)
        # only the 688-image train split (valid 197 + test 98 pass through
        # unaugmented, confirmed by matching the source project's raw split counts
        # exactly) - 2,063 of these 2,358 images carry baked-in Roboflow augmentation,
        # not ours, and are reported as such rather than folded into a "real" total
        # silently.
        "expect_images": 2358,
        "page_boxes": 1801,
        "rename": {"elephant": "Elephant"},
        "drop": {"water", "tree"},
    },
    # thai-elephant-dataset-v6 REMOVED 28 Aug - see ml/vision/README.md's "28 Aug -
    # bounding-box quality audit" entry. It was added specifically as the
    # "species-correct" structural fix for elephant-detection-cxnt1-v2's African-
    # elephant contamination (see that source's comment above). A direct 30-image
    # visual audit of this source found the opposite: roughly half the sample is
    # unmistakably African bush elephant morphology (fan ears past the shoulder,
    # concave back, savanna habitat), including one frame explicitly captioned
    # "ELEFANTE AFRICANO" in-image. Unlike elephant-detection-cxnt1-v2, this
    # source's filenames are opaque Roboflow-generated IDs (e.g.
    # "2902_jpg.rf.8ce97dca...") with no species-bearing text at all, so the
    # AFRICAN_ELEPHANT_FILENAME_MARKERS floor-filter that partly mitigates the
    # other source cannot catch any of this one's contamination - there is no
    # cheap filter available, only a full per-image visual reclassification,
    # which is not worth the time this close to the 2 Sept trial for a
    # supplement whose entire purpose was already better served by
    # wcs-elephas-maximus (real, species-verified, box-verified) and
    # asian-elephants-dataset-v1 (species-correct by construction, verified
    # clean on its own 9-image audit sample). Dropped entirely rather than
    # partially filtered. The already-uploaded 2,397 images are removed from
    # project 1097972 by scripts/cleanup_thai_elephant_vision.py, run once the
    # in-flight architecture sweep (recover.sh) finishes so the comparison
    # stays internally consistent - see the README entry for the before/after
    # retrain this produces.
    {
        "label": "Elephant",
        "slug": "wcs-elephas-maximus",
        "license": "CDLA-Permissive-1.0",
        "local_root": os.path.join(CACHE_DIR, "wcs-camera-traps", "elephas_maximus"),
        # 28 Aug finding, direct answer to "is African elephant data worth adding":
        # checked LILA BC's WCS Camera Traps set (1.37M images, 12 countries) for a
        # real species-correct source before considering any African-elephant
        # supplement. All 325 of its "elephas maximus" (Asian elephant, the correct
        # species) annotated images are from country_code "idn" - Indonesian forest
        # camera traps, a real tropical-forest domain match, not zoo/catalog
        # photography and not African savanna. 194/325 (60%) carry a real bounding
        # box in the companion wcs_20220205_bboxes_with_classes.json - same
        # real-box-only discipline as swg-eurasian-wild-pig below, for the same
        # reason (a whole-frame label with no box teaches the opposite of what we
        # want). Meaningful real night coverage: of the 194 boxed images, capture
        # hour (local camera time, no timezone conversion) shows a real spread
        # across 0-5 and 19-23, not just a token few - see fetch_wcs_elephant.py's
        # own printed breakdown. Small (194 images) but real, species-correct,
        # domain-matched, and box-verified - added on its merits, not as a
        # volume play. African-elephant sources (e.g. LILA's Nkhotakota, 10,664
        # images, of which 33,813 across the full set do carry manually drawn
        # boxes per LILA's own page - re-checked 28 Aug, correcting an earlier
        # wrong claim here that no box file existed) were deliberately NOT
        # added: box availability was never the real disqualifier. Training a
        # recall-critical detector on a morphologically different subspecies
        # (fan ears past the shoulder,
        # concave back, single-domed forehead - all absent in Kerala's Asian
        # elephants) risks teaching the wrong gestalt rather than reinforcing the
        # right one. Selected by scripts/fetch_wcs_elephant.py; run that first.
        # expect_images confirmed live 28 Aug: fetch_wcs_elephant.py downloaded
        # and pixel-verified all 194 candidates cleanly, zero failures.
        "expect_images": 194,
        "page_boxes": 194,
        "rename": {},
        "drop": set(),
    },
    {
        "label": "Elephant",
        "workspace": "wild-boar-fmkcg",
        "project": "night-ojblh",
        "version": 1,
        "slug": "night-ojblh-v1",
        "license": "CC BY 4.0",
        # 29 Aug find, user-supplied lead. Small (73 images, 1 version) but a
        # genuine thermal/IR camera-trap set, not RGB - visually confirmed via a
        # 12-image sample (all 12 opened): real low-res thermal-camera output
        # (bright heat-signature silhouette against a cooler dark background,
        # authentic thermal sensor noise pattern - nothing a stock/RGB source
        # would produce). ~6/12 unambiguous elephant (rear-view thermal
        # silhouette, several with a farm/perimeter fence rail visible in frame -
        # a striking domain match to this project's own forest-farm-boundary
        # deployment context), ~4/12 plausible wild-boar-shaped thermal blobs,
        # ~2/12 too low-resolution to call either way. Project declares a second
        # "wild-boar" class but it currently carries zero labeled instances (shown
        # disabled/dashed on the project page) - only the Elephant class is
        # actually annotated in this version, so wild-boar is dropped rather than
        # renamed. Confirmed live via --dry-run: the frozen v1 export carries 56
        # real Elephant boxes across 73 images (17 dropped as dropped_class - the
        # zero-instance wild-boar-tagged frames); the page's own 73-boxes figure
        # reflects the project's current live label state, not this frozen
        # export - same page-vs-export mismatch pattern as wild-boar-a1flm-v1.
        "expect_images": 73,
        "page_boxes": 73,
        "rename": {"elephant": "Elephant"},
        "drop": {"wild-boar"},
    },
    {
        "label": "Boar",
        "workspace": "trackabox-4ejy9",
        "project": "wild-boar-a1flm",
        "version": 1,
        "slug": "wild-boar-a1flm-v1",
        "license": "CC BY 4.0",
        "expect_images": 1901,
        # The project page reports 2,739 boxes; the v1 export carries 3,003, all of
        # them category "Pig". The page's per-class tally reflects the project's
        # current label state, not this frozen version - the export wins.
        "page_boxes": 2739,
        "rename": {"Pig": "Boar"},
        # The project declares a stray category literally named "`". It carries no
        # annotations in this export, but the guard stays so it can never sneak in.
        "drop": {"`"},
        # 28 Aug manual visual audit findings for this source - see the constant's
        # docstring above parse_coco(). Spot-check, not exhaustive.
        "exclude_filenames": BOAR_VISUALLY_CONTAMINATED_FILENAMES,
        # 28 Aug data-quality re-verification: see TV_BROADCAST_CLIP_PREFIXES above -
        # wb_framesb and wb_framesa00001 are both hunting-broadcast-show clips, not
        # field footage.
        "exclude_broadcast_clips": True,
    },
    {
        "label": "Boar",
        "workspace": "boarwatch",
        "project": "wild-boar-deterrent-pzq5t",
        "version": 1,
        "slug": "wild-boar-deterrent-pzq5t-v1",
        "license": "CC BY 4.0",
        "expect_images": 8857,
        "page_boxes": 13894,
        "rename": {"0": "Boar"},
        "drop": set(),
        # See the module docstring: this source's filenames are catalog-style
        # sequential IDs, not video-frame bursts, so group_key_exact() (Roboflow-
        # hash-suffix-only) is used instead of group_key()'s frame-tail stripping.
        "group_mode": "exact",
        # Brings Boar's total from 1,901 (trackabox alone) to 3,280 - Elephant's
        # exact count. One representative image is kept per sampled group.
        "sample_target": 1379,
        # 28 Aug manual visual audit findings for this source - see the constant's
        # docstring above DATASETS. Spot-check, not exhaustive.
        "exclude_filenames": BOAR_VISUALLY_CONTAMINATED_FILENAMES,
        # 28 Aug data-quality re-verification: wb_framesa00001 leaks into this
        # source too - see TV_BROADCAST_CLIP_PREFIXES above.
        "exclude_broadcast_clips": True,
    },
    {
        "label": "Boar",
        "workspace": "roboflow-100",
        "project": "trail-camera",
        "version": 2,
        "slug": "trail-camera-v2",
        "license": "CC BY 4.0",
        # 29 Aug finding, direct answer to the standing "prioritize real night/IR
        # camera-trap frames, not just species-matched daytime photos" instruction:
        # real Cuddeback-brand US game-camera trail imagery, day + IR-night, from
        # the Roboflow-100 benchmark collection. Categories are "game" (0 boxes in
        # this export), "Deer" (888 boxes), "Hog" (1,398 boxes, real Sus scrofa -
        # US feral hog, same species as Kerala's wild boar). Visually verified: a
        # seeded n=14 sample (seed 20260829) of Hog-annotated images opened with
        # boxes rendered - 14/14 genuine Sus scrofa, no deer or other species
        # mislabeled, box quality on par with the existing wild-boar-a1flm-v1
        # source. 8 of the 14 are real night/IR trigger frames (timestamps
        # spanning 12:18 AM-11:07 PM) - exactly the night-primary domain gap the
        # existing catalog-photo Boar sources lack. Recurring hunting-stand/feeder
        # structures in the background are a repeated visual element (a mild
        # spurious-correlation risk, same tier of caveat as any single-region
        # camera-trap set) but not disqualifying.
        "expect_images": 1311,
        "page_boxes": 1398,
        "rename": {"Hog": "Boar"},
        # "game" carries zero annotations in this export but is dropped
        # defensively, same discipline as the stray "`" guard on
        # wild-boar-a1flm-v1. Deer is real but off-species for this project - its
        # images fall through to zero-box Boar-source background records, same
        # treatment the elephant set's own stray non-elephant scenes get.
        "drop": {"Deer", "game"},
        # Two filename conventions coexist in this export: genuine single-trigger
        # timestamps ("20210828_204552...") and burst-sequence numbers
        # ("I__00113-1..."). group_key()'s default frame-tail collapse is correct
        # for the burst case but over-merges the timestamp case down to one group
        # per calendar date (all of one day's distinct trigger events become one
        # group) - a conservative diversity cost, not a leakage risk, and the
        # right side to err on per this pipeline's established preference (see
        # _FRAME_TAIL_NO_SEP's docstring above). No group_mode override.
    },
    {
        "label": "Boar",
        "slug": "wcs-sus-scrofa",
        "license": "CDLA-Permissive-1.0",
        "local_root": os.path.join(CACHE_DIR, "wcs-camera-traps", "sus_scrofa"),
        # 28 Aug finding: the same WCS Camera Traps set already used for
        # wcs-elephas-maximus above also carries real "sus scrofa" boxes - the
        # correct species (Kerala's wild boar and Indonesia/Laos's forest pig
        # are the same species, unlike the African/Asian elephant split). 831
        # boxed images total; country breakdown idn 734, lao 94, bol 3 - the 3
        # Bolivia records excluded (no native Sus scrofa range in South America,
        # almost certainly feral/domestic-descent, not the wild population this
        # project needs). 828 usable, real Southeast Asian forest camera-trap
        # imagery. Visually verified: a seeded n=10 sample rendered with boxes
        # and opened by eye - 6/10 unambiguous tightly-boxed wild boar, 4/10
        # lower quality (motion blur, flash blowout, fog) but still plausible
        # boar silhouettes, no wrong-species mislabels. Selected by
        # scripts/fetch_wcs_boar.py; run that first. expect_images confirmed
        # live 28 Aug: fetch_wcs_boar.py downloaded and pixel-verified all 828
        # candidates cleanly, zero failures (day/night split of the 828: 742
        # day, 65 night, 21 unknown/malformed timestamp).
        "expect_images": 828,
        "page_boxes": 828,
        "rename": {},
        "drop": set(),
    },
    {
        "label": "Boar",
        "workspace": "pig-rinoz",
        "project": "wild-pig-at-night",
        "version": 1,
        "slug": "wild-pig-at-night-v1",
        "license": "CC BY 4.0",
        # 28 Aug finding, direct answer to the standing "source more IR/night
        # data" instruction: small (64 images) but genuinely real IR/night
        # trail-cam footage - multiple camera brands visible in-frame (Bushnell,
        # Moultrie, "JonahCam"), real grayscale near-IR captures, unmistakable
        # wild boar including one frame showing a full sounder (adult + several
        # piglets) at a feeder. Visually verified: a 5-image sample pulled
        # directly from the public source.roboflow.com URLs (no export needed
        # to check) - 5/5 genuine night/IR camera-trap boar, no staged or
        # daytime-relabeled frames. Single class "wild-pig" in the source
        # project. The export's "largest clips" list flagged two filename
        # patterns as suspicious on a first pass - a literal "warthog"/
        # "domestic-pig" descriptive filename and a cluster of 12
        # "maxresdefault*"-prefixed files (YouTube's thumbnail-naming
        # convention). Both are stock-photo/non-field-footage red flags this
        # project has caught before, so all 13 flagged files were opened and
        # visually inspected directly rather than trusted or excluded on the
        # filename alone: all 13 (7 checked in full, the rest sharing the
        # same visual pattern) are genuine wild-boar IR trail-cam frames -
        # several carry authentic camera-trap timestamp/temperature overlays,
        # one even an ATN thermal-scope reticle overlay, which a stock-photo
        # pipeline would never produce. The "warthog"-tagged file is
        # unambiguously a wild boar, not a warthog - the filename's species
        # word is a bad auto-tag from whatever scraper produced it, not
        # evidence of contamination. The maxresdefault names are consistent
        # with these being frame-grabs re-scraped from trail-cam footage that
        # was itself uploaded to YouTube at some point - real pixels, just a
        # rehosted filename. No exclusion applied.
        "expect_images": 64,
        "page_boxes": 125,
        "rename": {"wild-pig": "Boar"},
        "drop": set(),
    },
    {
        "label": "Boar",
        "slug": "swg-eurasian-wild-pig",
        "license": "CDLA-Permissive-2.0",
        "local_root": os.path.join(CACHE_DIR, "swg-camera-traps", "eurasian_wild_pig"),
        # Real Southeast Asian forest camera-trap imagery (LILA BC SWG Camera Traps,
        # CDLA-Permissive-2.0, same Sus scrofa species) - the domain-match supplement
        # the plan's Phase 4 calls for, distinct from the catalog/deterrent-cam photos
        # the two sources above are. Selected and day/night-verified by
        # scripts/fetch_swg_camera_traps.py; run that first. expect_images is set
        # from that script's own printed real (pixel-verified) count, not assumed.
        "expect_images": None,
        "page_boxes": None,
        "rename": {},
        "drop": set(),
    },
    {
        "label": "Background",
        "slug": "swg-empty",
        "license": "CDLA-Permissive-2.0",
        "local_root": os.path.join(CACHE_DIR, "swg-camera-traps", "empty"),
        # Real forest camera-trap blanks, day and IR-night - every current
        # background image (the elephant set's 552) is an indoor/catalog scene, none
        # is a real forest camera-trap blank. Zero-box, same as those - Edge Impulse
        # doesn't care what label these are filed under, this is our own bookkeeping.
        "expect_images": None,
        "page_boxes": None,
        "rename": {},
        "drop": set(),
    },
    {
        "label": "Background",
        "slug": "board-captures-day1",
        "license": "N/A (own capture)",
        "local_root": os.path.join(_ROOT, "ml", "datasets", "vision", "raw", "board-captures-day1", "images"),
        # Real frames from the actual deployed camera (Arducam/IMX462 over the UNO
        # Q's USB capture path), not a proxy source - a blank-wall day scene, one
        # capture session. Low scene diversity (one wall, one lighting condition) by
        # construction; recorded as such, not inflated by treating it as more than
        # it is. Every frame stays one group (split_by_group), so this single scene
        # cannot straddle train/test.
        "expect_images": 26,
        "page_boxes": 0,
        "rename": {},
        "drop": set(),
    },
    {
        "label": "Background",
        "slug": "board-captures-night1",
        "license": "N/A (own capture)",
        "local_root": os.path.join(_ROOT, "ml", "datasets", "vision", "raw", "board-captures-night1", "images"),
        # Real IR-illuminated night frames from the same deployed camera as
        # board-captures-day1, its night counterpart - 29 Aug, four distinct
        # capture sessions through the user's own window (device could not yet
        # be field-mounted). Zero-box, same bookkeeping-only "Background" label
        # as every other true-negative source above; no elephant crossed the
        # frame, so this is a false-positive-rate source, not an Elephant-recall
        # source. Filenames carry an s1_/s2_/s3_/s4_ session prefix specifically
        # so group_key()'s trailing-number collapse keeps each physical framing
        # in its own group(s) - they cannot merge into one artificial mega-group
        # or straddle train/test with each other:
        #   s1_ (6 images)  - first IR status check, camera confirmed live
        #   s2_ (41 images) - clean framing, camera repositioned after two
        #                     earlier attempts caught window/glare artifacts
        #                     (deleted, never uploaded anywhere)
        #   s3_ (41 images) - same framing as s2_, room light off this time;
        #                     pixel stats close to s1_'s, room light was not
        #                     doing meaningful work in this scene
        #   s4_ (119 images) - continuous hand-panned burst, 201 raw frames
        #                     filtered to 119 by a numpy Laplacian-variance
        #                     sharpness cut (no cv2 available locally) - the
        #                     other 82 were motion-blurred mid-pan, dropped
        # A same-session near-duplicate check (mean consecutive-frame pixel
        # diff) found s3_ in particular is low-diversity - a near-static scene
        # oversampled 41x rather than 41 independent looks - worth thinning at
        # the next real re-upload rather than blocking this one on it.
        "expect_images": 207,
        "page_boxes": 0,
        "rename": {},
        "drop": set(),
    },
    {
        "label": "Elephant",
        "slug": "pseudo-ir-elephant",
        "license": "N/A (synthetic - derived from the real Elephant sources' own licenses above)",
        "local_root": os.path.join(_ROOT, "ml", "datasets", "vision", "pseudo_ir", "elephant"),
        # CANDAR 2023 grayscale+gamma+vignette recipe over real daytime Elephant
        # frames - scripts/make_pseudo_ir_vision.py, run that first. A supplement,
        # never a substitute for real IR footage (Phase 4, 3c-3) - synthetic=True
        # keeps it out of every "real data" total in the reporting below.
        "synthetic": True,
        "expect_images": None,
        "page_boxes": None,
        "rename": {},
        "drop": set(),
        # See _original_filename() / parse_coco - a contaminated source frame stays
        # contaminated after make_pseudo_ir_vision.py renames it.
        "filter_out_of_species": True,
        "exclude_broadcast_clips": True,
    },
    {
        "label": "Boar",
        "slug": "pseudo-ir-boar",
        "license": "N/A (synthetic - derived from the real Boar sources' own licenses above)",
        "local_root": os.path.join(_ROOT, "ml", "datasets", "vision", "pseudo_ir", "boar"),
        "synthetic": True,
        "expect_images": None,
        "page_boxes": None,
        "rename": {},
        "drop": set(),
        # See _original_filename() / parse_coco - a contaminated source frame stays
        # contaminated after make_pseudo_ir_vision.py renames it.
        "exclude_broadcast_clips": True,
    },
]

# Roboflow rewrites every exported filename as <stem>_<ext>.rf.<32 hex>.<ext>.
_RF_SUFFIX = re.compile(r"_(jpg|jpeg|png|bmp|webp)\.rf\.[0-9a-f]{6,}\.\w+$", re.IGNORECASE)
# A trailing frame counter, e.g. "wb_framesb--85-" -> clip "wb_framesb", "0004-124-" -> "0004".
_FRAME_TAIL = re.compile(r"^(.*?)[-_]+\d+$")
# 28 Aug finding: some video-frame-extraction tools (this exact case: the
# "elephant reaching into a stopped truck" clip inside elephant-detection-cxnt1-v2)
# emit frames as "frame0001.jpg" with no separator between the word and the
# counter, which _FRAME_TAIL never matches - every one of its 984 frames was
# falling through to its own singleton group and being shuffled independently
# across train/test, confirmed by cross-checking the real uploaded manifest
# (e.g. frame4340 landed in training, frame4349 nine frames later in testing) and
# by eye (a sampled contact sheet across the whole numeric range is the same
# truck-and-elephant scene start to finish - genuinely one clip, not several
# distinct sources sharing generic numbering). Deliberately narrow so it cannot
# repeat the Wild_Boar_NNNN over-merge mistake documented in the module
# docstring: requires a pure-alphabetic word (>=3 letters) directly followed by
# a real counter (>=2 digits) and nothing else, so opaque hex/alphanumeric
# filenames (e.g. "000a6c3a2c4d97e7", which starts with a digit and interleaves
# letters and digits throughout) never match and stay singleton, as verified
# against every current DATASETS source before landing this.
_FRAME_TAIL_NO_SEP = re.compile(r"^([A-Za-z]{3,}?)\d{2,}$")


def _request(url, api_key=None, method="GET", body=None):
    headers = {}
    if api_key:
        headers["x-api-key"] = api_key
    if body is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(body).encode()
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def ensure_object_detection(project_id, api_key):
    """Flip the project to bounding-box labeling; bbox ingestion is lossy otherwise.

    A fresh Edge Impulse project defaults to labelingMethod "single_label", which
    ignores the boundingBoxes in an upload. This is checked, not assumed.
    """
    info = _request(f"{STUDIO}/{project_id}", api_key=api_key)
    project = info.get("project", {})
    current = project.get("labelingMethod")
    print(f"Edge Impulse project {project_id} ({project.get('name')}): labelingMethod={current}")
    if current == "object_detection":
        return
    _request(
        f"{STUDIO}/{project_id}",
        api_key=api_key,
        method="POST",
        body={"labelingMethod": "object_detection"},
    )
    print(f"  changed labelingMethod {current!r} -> 'object_detection'")


def roboflow_export_link(ds, rf_key):
    """Ask Roboflow for a COCO export of one dataset version, waiting if it is generating."""
    url = f"{ROBOFLOW}/{ds['workspace']}/{ds['project']}/{ds['version']}/coco?api_key={rf_key}"
    for attempt in range(MAX_RETRIES):
        doc = _request(url)
        export = doc.get("export") or {}
        if export.get("link"):
            return export["link"], export.get("size")
        wait = 15 * (attempt + 1)
        print(f"  export still generating (progress={doc.get('progress')}), waiting {wait}s")
        time.sleep(wait)
    raise RuntimeError(f"{ds['slug']}: Roboflow never returned an export link")


def fetch_dataset(ds, rf_key):
    """Download + extract one dataset version, reusing the cache when it is intact.

    A "local_root" entry (scripts/fetch_swg_camera_traps.py's output, or a real
    board-captured frame directory) skips Roboflow entirely - the directory already
    holds its own _annotations.coco.json in the same shape, built by whatever
    script populated it, and just needs to exist.
    """
    if ds.get("local_root"):
        if not os.path.isdir(ds["local_root"]):
            raise RuntimeError(
                f"{ds['slug']}: local_root {ds['local_root']} does not exist - "
                "run its producing script first (see the DATASETS entry's comment)"
            )
        return ds["local_root"]

    os.makedirs(CACHE_DIR, exist_ok=True)
    zip_path = os.path.join(CACHE_DIR, f"{ds['slug']}-coco.zip")
    out_dir = os.path.join(CACHE_DIR, ds["slug"])

    link, size_mb = roboflow_export_link(ds, rf_key)
    # Roboflow reports the export size in megabytes (1e6 bytes), not mebibytes.
    expect_bytes = int(size_mb * 1e6) if size_mb else None
    have = os.path.getsize(zip_path) if os.path.exists(zip_path) else 0
    if have and (expect_bytes is None or abs(have - expect_bytes) < max(1024, expect_bytes * 0.01)):
        print(f"  cached {os.path.basename(zip_path)} ({have / 1e6:.1f} MB) - skipping download")
    else:
        print(f"  downloading {size_mb:.1f} MB -> {zip_path}")
        urllib.request.urlretrieve(link, zip_path)
        print(f"  downloaded {os.path.getsize(zip_path) / 1e6:.1f} MB")

    if os.path.isdir(out_dir):
        print(f"  already extracted at {out_dir}")
    else:
        print(f"  extracting -> {out_dir}")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(out_dir)
    return out_dir


def group_key(fname):
    """Collapse a Roboflow filename to the source clip it came from.

    Strips Roboflow's "_jpg.rf.<hash>.jpg" rewrite, then one trailing frame
    counter, so consecutive frames of one clip share a key and never straddle
    the train/test boundary. Standalone photos keep their own stem and stay
    their own single-image group. Falls back to _FRAME_TAIL_NO_SEP for the
    no-separator "frame0001" naming convention (see its comment above) only
    when the primary pattern does not match at all.
    """
    stem = os.path.splitext(_RF_SUFFIX.sub("", fname))[0].rstrip("-_ ")
    match = _FRAME_TAIL.match(stem)
    if match and match.group(1):
        return match.group(1)
    match = _FRAME_TAIL_NO_SEP.match(stem)
    return match.group(1) if match and match.group(1) else stem


def group_key_exact(fname):
    """Like group_key(), but without the trailing-frame-number collapse.

    Correct for sources whose filenames are catalog-style sequential IDs
    (Wild_Boar_0001, Wild_Boar_0002, ... - each number a different source photo)
    rather than genuine consecutive video frames. Applying group_key() there
    would merge hundreds of distinct photos into one artificial mega-group. Same-
    photo re-exports (identical stem, different resolution) still collapse into
    one group, since only Roboflow's own hash suffix is stripped.
    """
    return os.path.splitext(_RF_SUFFIX.sub("", fname))[0].rstrip("-_ ")


def sample_by_group(records, target, label, live_categories=None, seed=SPLIT_SEED):
    """Pick one representative image from each of a shuffled subset of groups.

    Used to bring a heavily-grouped source down to a target image count while
    maximizing real visual diversity per image added: one image per group beats
    many images from few groups, since within-group images are re-exports of the
    same photo. Groups not already live are consumed in seeded-shuffle order
    until target images are selected or groups run out.

    live_categories (sha256 -> category, from fetch_live_content_categories)
    locks in any group that already has a member stored live, regardless of the
    shuffle or the target count - the same append-only discipline
    split_by_group uses and for the same reason. This function's own seeded
    shuffle depends on the full current group-key list (random.Random(seed)
    .shuffle(keys) is sensitive to that list's content, not just its length),
    so any unrelated change to the source's record set - a new
    exclude_filenames entry, a re-fetch - reshuffles which groups get picked,
    silently dropping a group that was selected and uploaded in a past run even
    though nothing about that specific group changed. This was live and
    unnoticed for one source (wild-boar-deterrent-pzq5t-v1's sample_target)
    until the 29 Aug reconciliation-gap investigation traced a ~100-image
    total-count mismatch to it - the exact same bug class already fixed in
    split_by_group, one pipeline stage earlier, previously invisible because
    this function ran before content hashes were even computed.
    """
    groups = {}
    for rec in records:
        groups.setdefault(rec["group"], []).append(rec)

    live_categories = live_categories or {}

    def _rep_for(key):
        members = groups[key]
        live_member = next((r for r in members if r.get("_sha256") in live_categories), None)
        if live_member is not None:
            return live_member
        return sorted(members, key=lambda r: r["name"])[0]

    locked_keys = sorted(
        key for key, members in groups.items()
        if any(r.get("_sha256") in live_categories for r in members)
    )
    new_keys = sorted(k for k in groups if k not in set(locked_keys))
    random.Random(seed).shuffle(new_keys)

    selected = [_rep_for(key) for key in locked_keys]
    for key in new_keys:
        if len(selected) >= target:
            break
        selected.append(_rep_for(key))

    print(
        f"  {label}: sampling {target} of {len(groups)} groups "
        f"({len(records)} raw images) -> {len(selected)} images selected "
        f"({len(locked_keys)} locked to their live-stored group, {len(new_keys)} new "
        f"groups shuffled with seed {seed}, 1 representative image/group)"
    )
    if len(selected) < target and len(new_keys) < target - len(locked_keys):
        print(
            f"    NOTE: only {len(groups)} groups exist, target {target} not reached "
            f"({target - len(selected)} short)"
        )
    return selected


_LEADING_DIGITS = re.compile(r"(\d+)")


def _numeric_sort_key(name):
    """Sort key that orders an embedded frame counter numerically (frame2
    before frame10) rather than lexically, falling back to plain string order
    for anything with no digits at all.
    """
    match = _LEADING_DIGITS.search(name)
    return (int(match.group(1)) if match else -1, name)


def cap_named_group(records, group_name, cap, label, seed=SPLIT_SEED):
    """Cut one specific oversized, low-diversity group down to `cap`
    representative images, spread evenly across the group's numeric frame
    order, while leaving every other group in the dataset fully intact.

    Built for elephant-detection-cxnt1-v2's "frame" clip (984 images, a
    single continuous dashcam sequence - the viral RAJAMURUGAN "elephant
    reaching into a stopped truck" video, baked-in "U TURN" overlay text) per
    the user's 28 Aug decision on the frame-clip audit finding: keep it as
    legitimate training data (it is a real elephant, not a species/broadcast
    defect the filters above exist to catch) but cut its ~39% share of the
    whole source down from duplication to a handful of representative frames,
    the same discipline sample_by_group() already applies dataset-wide for
    wild-boar-deterrent-pzq5t-v1, scoped here to one named group instead of
    every group. Evenly spread by frame number (not a random seeded draw)
    so the frames kept actually span the scene's distinct beats - approach,
    reach, retreat - rather than risking a random draw clustering within one
    beat; the seed parameter is accepted for interface symmetry with
    sample_by_group() but unused, since the selection is deterministic by
    construction.
    """
    del seed
    others = [r for r in records if r["group"] != group_name]
    members = sorted(
        (r for r in records if r["group"] == group_name),
        key=lambda r: _numeric_sort_key(r["name"]),
    )
    if len(members) <= cap:
        return records
    idxs = sorted({round(i * (len(members) - 1) / (cap - 1)) for i in range(cap)})
    selected = [members[i] for i in idxs]
    print(
        f"  {label}: capping group '{group_name}' from {len(members)} to "
        f"{len(selected)} images (evenly spread by frame number, "
        f"{len(members) - len(selected)} dropped)"
    )
    return others + selected


def _sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256(path):
    """Second, independent hash of the same file - Edge Impulse's own listSamples
    API reports sha256Hash per stored sample (confirmed in the live OpenAPI spec),
    not sha1. This is what fetch_live_content_categories matches against; the
    existing sha1 in dedupe_by_content stays untouched to avoid touching working
    behavior for an unrelated reason.
    """
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def dedupe_by_content(records, label, content_seen):
    """Drop every record that is byte-for-byte identical to one already kept for
    this label - including across different source datasets, since content_seen
    is shared across the whole main() loop rather than reset per dataset.

    Edge Impulse's own ingestion API already rejects exact-duplicate content
    server-side (x-disallow-duplicates) - relying on that round-trip to size
    "expected" is what the original reconciliation bug did, and it cannot
    distinguish a genuine new duplicate from a resend of content this exact run
    already uploaded. Hashing locally, once, before the split is computed, makes
    "expected" correct by construction: no manifest count can ever list more
    images than the project can actually end up storing. This is the same check
    previously done by hand with SHA1 outside this script (see
    reconcile_project_counts's docstring) - now built in.
    """
    kept, dupes = [], []
    for rec in records:
        digest = _sha1(rec["path"])
        prior = content_seen.get((label, digest))
        if prior is not None:
            dupes.append((rec["name"], prior))
            continue
        content_seen[(label, digest)] = rec["name"]
        kept.append(rec)
    return kept, dupes


# 27 Aug 3a species-verification finding (ml/vision/README.md): a full-population
# filename scan of elephant-detection-cxnt1-v2 found these terms naming an African
# range country/park in 34 of its 3,280 filenames (e.g.
# "african-elephants-crossing-road-zimbabwe...", "elephant-kenya-africa-amboseli-
# reserve..."). Deliberately a floor, not a full species classifier - it only
# catches images whose own filename admits the species, which is why the finding
# also flags this as undercounting the true contamination rate.
AFRICAN_ELEPHANT_FILENAME_MARKERS = (
    "namibia", "kenya", "tanzania", "kruger", "etosha", "amboseli", "zimbabwe",
    "serengeti", "africa",
)


def _is_named_african_elephant(filename):
    lower = filename.lower()
    # 28 Aug data-quality re-verification, fourth pass: diag_reconcile_vision.py's
    # live/manifest orphan report turned up 552 elephant-detection-cxnt1-v2 filenames
    # (233 "af_<id>", 319 "as_<id>") not caught by any filter above - a species-code
    # naming convention from a different uploader than the rest of the source, not
    # the same "images<N>_" generic-scrape shape. A seeded sample of 10 of each
    # prefix, boxes rendered, opened by eye: af_ came back 6/6 unmistakable African
    # bush elephant (fan ears well past the shoulder, tusked in both sexes, savanna
    # grassland/waterhole habitat, concave/sway back) - genuine species contamination,
    # same defect this function already exists to catch, just a naming convention it
    # didn't know about. as_ came back consistent with real Asian elephant (small
    # crumpled ears, bilobed forehead) - correct species, left alone; one of the six
    # (as_tr14) is visibly captive/enclosure (fencing, hay bedding) rather than field
    # photography, a domain concern worth a future pass but not a species defect and
    # not excluded here, consistent with this file not otherwise filtering captive
    # Elephant content the way BOAR_VISUALLY_CONTAMINATED_FILENAMES does for Boar.
    if lower.startswith("af_"):
        return True
    return any(marker in lower for marker in AFRICAN_ELEPHANT_FILENAME_MARKERS)


# 28 Aug data-quality re-verification (ml/vision/README.md): a user-caught broadcast
# screenshot prompted a re-check of this source, which turned up a real gap in the
# marker filter above - it only catches filenames that name a place, and this
# dataset's African-elephant contamination is dominated by generic-captioned safari
# stock photography ("elephant-crossing-road-<id>", depositphotos/shutterstock IDs)
# that names no place at all. Every filename below was opened and visually confirmed
# African bush elephant (fan ears past the shoulder, concave/sway back). The same
# "crossing-road" naming genre also contains genuinely Asian images - a real Kerala
# corridor (Tirunelli-Kudrakote) and a Yala National Park, Sri Lanka frame among
# them - which is exactly why this is an explicit visually-audited list, the same
# discipline as BOAR_VISUALLY_CONTAMINATED_FILENAMES below, and not a keyword or
# substring rule that would also drop those two.
AFRICAN_ELEPHANT_VISUALLY_CONFIRMED_FILENAMES = frozenset({
    "depositphotos_33832091-stock-photo-elephants-crossing-road_jpg.rf.7978135963ebb1b2244fa4aa1ccb1545.jpg",
    "elephant-crossing-road-260nw-2131250923_jpg.rf.780290af570f88969574730469fb3950.jpg",
    "elephant-crossing-road-park-south-260nw-2060208290_jpg.rf.7ee3b45613470dacd1e565e80385082c.jpg",
    "elephants-crossing-road-stock-photo_csp7850002_jpg.rf.9d2083932e21cd5d43b8ad5cef4e90fa.jpg",
    "baby-elephant-crossing-road-alone-260nw-1888404427_jpg.rf.ac7f1046dc41a6c23c72fd177ab7ef31.jpg",
    "elephant-crossing-road-2078811_jpg.rf.f95fee184153e0de38f3cfa659eab130.jpg",
    "focused_178065536-stock-photo-elephant-crossing-road-safari-countryside_jpg.rf.cf8ef791e9c634a460080ba24bbba3e5.jpg",
    "210127-elephant-crossing-road_jpg.rf.de4523c542c0a95bf4159c8420740372.jpg",
    "PICHA_PHOT01183-9967__Elephants_Crossing_Road_2_jpg.rf.e9531c4bfc838384ba7124b0bcdd2e6d.jpg",
    "cute-elephant-calf-crossing-road-260nw-1292553694_jpg.rf.3bb74b57dff640b9ef8e369ff9ad8fad.jpg",
    "elephant-crossing-road-12267234_jpg.rf.b8d0840046f8734d14860bafccc5041b.jpg",
    "elephant-crossing-road-20777933_jpg.rf.7d6fd24f14a7abb9ef6b086305d61f35.jpg",
    # 29 Aug data-quality re-verification: the checks above only cover filenames
    # that name a place or match the "crossing-road" stock-caption genre. A full
    # scan turned up a third, disjoint naming shape in this source - bare
    # Roboflow-auto-numbered frames ("<N>_jpg.rf.<hash>.jpg", no place name, no
    # caption text) - 142 filenames matching this shape uncaught by any filter
    # above. Unlike the "images<N>_" generic-scrape bucket (0/16 usable, handled
    # by a blanket pattern), this bucket is a genuine mix of real Asian field
    # photography and contamination, so it gets the same explicit visually-
    # audited-list treatment as this constant already uses, not a pattern rule.
    # All 142 were opened by eye (6 contact sheets, red box overlays burned in).
    # The nine below are unmistakable African bush elephant - large fan ears
    # extending well past the shoulder, tusked adults, savanna/waterhole/dry-
    # woodland habitat, several with a visible safari vehicle or multi-animal
    # herd line that settles any doubt at a glance.
    "11_jpg.rf.4374c3a01c2bf24c96b649510ad86544.jpg",  # 3 elephants, safari vehicle visible, dirt road
    "20_jpg.rf.76e4328a055eb5f3c861eaba6602d137.jpg",  # large adult walking at camera, huge ear fans
    "21_jpg.rf.d1876fdba2c04bb37f51c6cb8cdb999b.jpg",  # herd at waterhole, unmistakable fan ears
    "24_jpg.rf.11da1f8a520b9b0fe4c5318a810c77b0.jpg",  # 3 elephants, dry savanna woodland, baobab-style trees
    "1_jpg.rf.0b13f9349f0c40782616c8e31ddbbed8.jpg",  # 4-elephant line at a waterhole
    "38_jpg.rf.9a8a8100ef2a939114049b056359e7c0.jpg",  # 5+ herd at waterhole, large fan ears, tusks
    "39_jpg.rf.58b6aa93179ab5e93f77cb764e637ab3.jpg",  # also carries an "africanimagelibrary.com" watermark
    "55_jpg.rf.f052c70327b8f025384a924c01140779.jpg",  # single large adult, side profile, fan ears past shoulder
    "76_jpg.rf.48eb47f55e0de667157139bd0216f8d8.jpg",  # frontal, massive fan ears, dry bush habitat
})


# 28 Aug data-quality re-verification (ml/vision/README.md): elephant-detection-cxnt1-v2
# is frame-extracted from ~40 video clips, one filename prefix (text before the first
# "-") per clip. Sampled one frame from each of the ten largest clips by frame count
# and found nine are Thai TV news broadcast screen-captures - visible channel bugs
# (MCOT HD, Thairath TV, Amarin, "THE WORLD", "สำรวจโลก"), live tickers, Thai-caption
# lower-thirds, anchor picture-in-picture - baked into the pixels, not direct
# photography. Only clips actually opened and confirmed by eye are listed; the ~30
# smaller clips in this source have not been sampled and are not covered here - see
# the README entry for what that means for coverage.
TV_BROADCAST_CLIP_PREFIXES = frozenset({
    "0003", "E026", "0011", "a003", "0008", "0009", "0007", "0005", "0010", "5460",
    # 28 Aug data-quality re-verification, Boar side: "wb_framesb--<N>-..." and
    # "wb_framesa00001-<N>-..." are both genuine video-frame sequences (per
    # group_key()'s frame-tail stripping, built for exactly this naming), but
    # visually opened by eye they are hunting-broadcast-show footage - baked-in
    # channel bug and lower-third, same defect this list already exists to catch,
    # not camera-trap or direct field photography. wb_framesb is confirmed only
    # in wild-boar-a1flm-v1; wb_framesa00001 leaks into both wild-boar-a1flm-v1
    # and wild-boar-deterrent-pzq5t-v1, so exclude_broadcast_clips is turned on
    # for every Boar source below, not just the one it was first found in.
    "wb_framesb", "wb_framesa00001",
})


def _is_tv_broadcast_clip(filename):
    return filename.split("-", 1)[0] in TV_BROADCAST_CLIP_PREFIXES


# 28 Aug data-quality re-verification, third pass: the prefix check above only
# catches elephant-detection-cxnt1-v2's hyphen-prefixed clip frames
# ("0005-174-..."). A full-population filename scan found a second, disjoint
# naming shape in the same source - generic uploader names "Image<N>_..." /
# "images<N>_..." with no hyphen before the first digit run, so
# _is_tv_broadcast_clip's split("-", 1)[0] never matches anything in
# TV_BROADCAST_CLIP_PREFIXES for these (the whole filename becomes the
# "prefix"). 164 filenames match this shape across train/test/valid (124/7/33).
# A seeded (random.Random(20260822)) sample of 16 of the 164 - drawn from the
# same pool the split actually trains on, boxes rendered and each image opened
# by eye - came back 16/16 not usable: 10 Thai TV news broadcast screen-
# captures (TNN, Thairath TV 32 - channel bugs, live tickers, anchor
# picture-in-picture), 1 a scanned stock-photo book cover ("Identification
# Guide for Ivory and Ivory Substitutes"), 1 a watermarked Alamy stock photo,
# and 3 clean-looking but generic safari stock photography of African bush
# elephant (fan ears past the shoulder, tusked adults, savanna grassland/road
# backdrop - not Asian elephant, not camera-trap imagery, the same species
# problem AFRICAN_ELEPHANT_VISUALLY_CONFIRMED_FILENAMES exists to catch, just
# not filename-markable the same way). Zero of 16 were real Asian-elephant
# field photography. Given 0/16 clean from a population of 164, treating the
# whole naming shape as contaminated is far safer than trying to whitelist the
# unsampled 148 - the same "when in doubt, exclude" call this file already
# makes for BOAR_VISUALLY_CONTAMINATED_FILENAMES. Scoped as its own flag
# (rather than folded into exclude_broadcast_clips) because the drop reason is
# broader than broadcast - it is "not a real Asian-elephant field frame" - and
# because only elephant-detection-cxnt1-v2 uses this generic naming
# convention; no other source's real filenames are known to collide with it.
_GENERIC_UPLOADER_NAME = re.compile(r"^[Ii]mages?\d+_")


def _is_generic_named_scrape(filename):
    return bool(_GENERIC_UPLOADER_NAME.match(filename))


# 28 Aug data-quality re-verification, second pass: scripts/make_pseudo_ir_vision.py
# renames every frame it touches to "pseudoir_<counter>_<original file name>", so a
# contaminated source frame does not stop being contaminated once it is greyscaled
# and re-rendered as synthetic IR - it just stops matching the filters above, which
# are keyed on the real source's naming. Confirmed live: 17 of 251 pseudo-ir-elephant
# frames (6.8%) are derived from one of the ten confirmed TV-broadcast clips above
# (verified by listing ml/datasets/vision/pseudo_ir/elephant against
# TV_BROADCAST_CLIP_PREFIXES); zero matched the African-stock-photo list. Strip the
# prefix before running either check so a synthetic derivative is judged on the
# source frame it actually came from.
_PSEUDO_IR_PREFIX = re.compile(r"^pseudoir_\d+_")


def _original_filename(filename):
    return _PSEUDO_IR_PREFIX.sub("", filename, count=1)


def parse_coco(root, ds):
    """Read every _annotations.coco.json under root into EI-shaped records.

    Roboflow writes one annotation file per split directory. All of them are
    merged here because this script does its own group-aware split; Roboflow's
    own train/valid/test division is discarded (and for the boar set there is
    none - all 1,901 images sit in train).
    """
    group_fn = group_key_exact if ds.get("group_mode") == "exact" else group_key
    records = []
    drops = {
        "zero_area": 0,
        "degenerate_area": 0,
        "dropped_class": 0,
        "missing_file": 0,
        "species_contaminated": 0,
        "visually_contaminated": 0,
        "tv_broadcast": 0,
        "generic_named_scrape": 0,
        "unreliable_zero_box": 0,
    }
    background = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        if "_annotations.coco.json" not in filenames:
            continue
        with open(os.path.join(dirpath, "_annotations.coco.json")) as fh:
            doc = json.load(fh)
        # Roboflow emits a root supercategory ("supercategory": "none") that never
        # carries annotations; keep only the real leaf classes.
        leaves = {
            c["id"]: c["name"]
            for c in doc.get("categories", [])
            if c.get("supercategory", "none") != "none"
        }
        cats = leaves or {c["id"]: c["name"] for c in doc.get("categories", [])}
        images = {img["id"]: img for img in doc.get("images", [])}

        by_image = {}
        for ann in doc.get("annotations", []):
            raw = cats.get(ann["category_id"])
            if raw is None or raw in ds["drop"]:
                drops["dropped_class"] += 1
                continue
            img = images.get(ann["image_id"])
            if img is None:
                continue
            x, y, w, h = (round(v) for v in ann["bbox"])
            x, y = max(0, x), max(0, y)
            w, h = min(w, img["width"] - x), min(h, img["height"] - y)
            if w <= 0 or h <= 0:
                drops["zero_area"] += 1
                continue
            if (w * h) / (img["width"] * img["height"]) < MIN_BOX_AREA_FRACTION:
                drops["degenerate_area"] += 1
                continue
            by_image.setdefault(ann["image_id"], []).append(
                {"label": ds["rename"].get(raw, raw), "x": x, "y": y, "width": w, "height": h}
            )

        for img_id, img in images.items():
            source_name = _original_filename(img["file_name"])
            if ds.get("filter_out_of_species") and _is_named_african_elephant(source_name):
                drops["species_contaminated"] += 1
                continue
            if ds.get("filter_out_of_species") and source_name in AFRICAN_ELEPHANT_VISUALLY_CONFIRMED_FILENAMES:
                drops["species_contaminated"] += 1
                continue
            if ds.get("exclude_broadcast_clips") and _is_tv_broadcast_clip(source_name):
                drops["tv_broadcast"] += 1
                continue
            if ds.get("exclude_generic_named_scrape") and _is_generic_named_scrape(source_name):
                drops["generic_named_scrape"] += 1
                continue
            if img["file_name"] in ds.get("exclude_filenames", ()):
                drops["visually_contaminated"] += 1
                continue
            # An image with no boxes is a deliberate negative, not a defect: the
            # elephant set ships 552 non-elephant scenes (casino, hospital-corridor,
            # Kindergarden_classroom, pantry...). Uploaded with an empty
            # boundingBoxes list, they are exactly the background examples FOMO
            # needs to learn what "no animal" looks like, so they are kept.
            boxes = by_image.get(img_id, [])
            if not boxes:
                # unreliable_zero_box is for a source whose own class list is not
                # trustworthy enough to certify "no box here" as "nothing here" - e.g.
                # a classmap with duplicate or garbage pseudo-classes mixed in with the
                # real species classes, where a frame with zero surviving boxes might
                # genuinely be empty, or might be a real animal whose annotation landed
                # on a garbage category. Uploading those as confirmed background risks
                # teaching the detector that a visible animal silhouette is nothing -
                # skip the image entirely instead of guessing. No live DATASETS entry
                # uses this yet (29 Aug: praveenmn75/elephant-thermal was the candidate
                # that motivated it, but was rejected outright on other grounds before
                # this flag was needed - see ml/vision/README.md) - kept as
                # infrastructure for the next source with the same defect.
                if ds.get("unreliable_zero_box"):
                    drops["unreliable_zero_box"] += 1
                    continue
                background += 1
            path = os.path.join(dirpath, img["file_name"])
            if not os.path.exists(path):
                drops["missing_file"] += 1
                continue
            records.append(
                {
                    "path": path,
                    "name": img["file_name"],
                    "group": group_fn(img["file_name"]),
                    "boxes": boxes,
                }
            )
    records.sort(key=lambda r: r["name"])
    return records, drops, background


def split_by_group(records, label, live_categories=None):
    """Assign whole source-clip groups to training/testing at ~80/20.

    live_categories (sha256 -> "training"/"testing", from
    fetch_live_content_categories) takes priority over the shuffle: a group
    whose every record already exists live keeps its live category, full stop -
    it is never reshuffled. Only groups with no live match at all ("new" groups)
    go through the seeded shuffle, sized against whatever test-fraction budget
    the already-locked groups haven't already used up. This is what makes the
    split append-only - see fetch_live_content_categories's docstring for the
    reconciliation failure this fixes and why recomputing from scratch every run
    cannot be trusted once a dataset has grown across more than one upload.
    """
    if not records:
        # A source can legitimately parse to zero images (a producing script
        # still mid-run, or genuinely empty) - report that plainly rather than
        # letting the percentage math below divide by zero.
        print(f"  {label}: 0 images - nothing to split")
        return {}, 0

    live_categories = live_categories or {}
    groups = {}
    for rec in records:
        groups.setdefault(rec["group"], []).append(rec)

    locked = {}  # group key -> category, decided from live content, never reshuffled
    conflicts = 0
    for key, members in groups.items():
        seen = {live_categories[r["_sha256"]] for r in members if r.get("_sha256") in live_categories}
        if not seen:
            continue
        if len(seen) > 1:
            # Some of this group's images are live as training, others as testing -
            # a real inconsistency (most likely from a split computed before this
            # fix existed). Lock to whichever category holds the majority of this
            # group's already-live records so the group stays whole, and surface it
            # rather than silently picking one.
            counts = {}
            for r in members:
                cat = live_categories.get(r["_sha256"])
                if cat:
                    counts[cat] = counts.get(cat, 0) + 1
            majority = max(counts, key=counts.get)
            print(
                f"    WARNING: group '{key}' ({label}) is split live between "
                f"{dict(counts)} - locking the whole group to '{majority}', the majority"
            )
            locked[key] = majority
            conflicts += 1
        else:
            locked[key] = next(iter(seen))

    new_keys = sorted(k for k in groups if k not in locked)
    random.Random(SPLIT_SEED).shuffle(new_keys)

    locked_test_n = sum(len(groups[k]) for k, cat in locked.items() if cat == "testing")
    target = len(records) * TEST_FRACTION
    testing = {k for k, cat in locked.items() if cat == "testing"}
    n_test = locked_test_n
    for key in new_keys:
        size = len(groups[key])
        if n_test + size <= target * TEST_OVERSHOOT:
            testing.add(key)
            n_test += size
    for rec in records:
        rec["category"] = "testing" if rec["group"] in testing else "training"

    clustered = sum(len(v) for v in groups.values() if len(v) > 1)
    biggest = sorted(((len(v), k) for k, v in groups.items()), reverse=True)[:4]
    print(f"  {label}: {len(records)} images in {len(groups)} groups (seed {SPLIT_SEED})")
    print(
        f"    {len(locked)} groups locked to their live-stored category"
        f"{f' ({conflicts} had a live train/test conflict)' if conflicts else ''}, "
        f"{len(new_keys)} new groups freshly assigned"
    )
    print(f"    largest clips: {', '.join(f'{k} x{n}' for n, k in biggest)}")
    print(f"    {clustered} images ({clustered / len(records) * 100:.0f}%) sit in multi-image clips")
    print(
        f"    training {len(records) - n_test} / testing {n_test} "
        f"({n_test / len(records) * 100:.1f}% held out)"
    )
    if clustered < len(records) * 0.05:
        print(
            "    WARNING: almost every group holds a single image - grouping is a near no-op "
            "here and this split is effectively random. Carry that into the README."
        )
    return groups, clustered


def _content_type(name):
    ext = os.path.splitext(name)[1].lower()
    return {".png": "image/png", ".bmp": "image/bmp", ".webp": "image/webp"}.get(ext, "image/jpeg")


def _multipart(parts):
    """Encode (filename, content_type, bytes) parts as one multipart/form-data body.

    Every part uses the field name "data", which is what the ingestion API's files
    endpoint expects - including for the bounding_boxes.labels part that rides
    along in the same batch and carries the labels for the images beside it.
    """
    boundary = f"----EleTectX{random.getrandbits(64):016x}"
    body = bytearray()
    for fname, ctype, data in parts:
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="data"; filename="{fname}"\r\n'.encode()
        body += f"Content-Type: {ctype}\r\n\r\n".encode()
        body += data + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return boundary, bytes(body)


def _parse_ingest_response(raw, sent_names):
    """Turn the ingestion API's per-file body into accepted/rejected name lists.

    The old code did resp.read() and returned None, treating a 2xx HTTP status as
    proof every file in the batch landed. It does not: with x-disallow-duplicates
    set, a byte-identical file already in the project is reported inside this body
    as a per-file rejection while the HTTP status stays 200.

    The real response shape, confirmed against a live probe request (not assumed
    from docs, which don't document the batch shape at all): {"success": bool,
    "files": [...]}, where "files" is POSITIONAL - one entry per image file in the
    exact order they were sent in this request, with the bounding_boxes.labels
    part not itself represented - and entries carry no filename field of any kind.
    A success entry looks like {"success": true, "projectId", "sampleId",
    "fileName"} (fileName has a random suffix appended, not the original name); a
    rejection looks like {"success": false, "error": "..."}, e.g. "An item with
    this hash already exists (ids: 12345)" for a duplicate. A prior version of
    this function matched on entry.get("file") or entry.get("name") - both absent
    from this real shape - so every entry fell through to "unaccounted for" and
    misclassified 100% of a real 6,560-image re-upload as rejected even though
    most of it landed. sent_names must be given in the same order the image parts
    were appended to the request body.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print("    WARNING: ingestion response was not JSON, assuming full batch accepted")
        return {"accepted": list(sent_names), "rejected": []}

    files = data.get("files")
    if not isinstance(files, list):
        print("    WARNING: ingestion response has no 'files' breakdown, assuming full batch accepted")
        return {"accepted": list(sent_names), "rejected": []}

    if len(files) != len(sent_names):
        print(
            f"    WARNING: ingestion response listed {len(files)} file results for "
            f"{len(sent_names)} sent - positional matching can't be trusted for this "
            "batch, treating every sent file as unaccounted for"
        )
        return {
            "accepted": [],
            "rejected": [(name, "response file count did not match batch size") for name in sent_names],
        }

    accepted, rejected = [], []
    for name, entry in zip(sent_names, files):
        if entry.get("success"):
            accepted.append(name)
        else:
            rejected.append((name, entry.get("error") or "rejected, no reason given"))
    return {"accepted": accepted, "rejected": rejected}


def upload_batch(api_key, category, batch):
    """POST one batch of images plus their bounding_boxes.labels to the ingestion API.

    Returns a dict {"accepted": [...], "rejected": [(name, reason), ...]} once the
    HTTP request itself completes, however individual files within it fared - or a
    (code, detail) tuple if the request itself failed after retries. Callers must
    check which shape came back (isinstance(result, tuple)) before use.
    """
    # The legacy "bounding_boxes.labels" schema - a flat filename -> boxes map under
    # an explicit type - is the one this endpoint accepts. The newer "info.labels"
    # files[] shape documented on the annotation spec page is rejected here: sent
    # under this filename it fails with {"error":"Invalid type"}, and sent as
    # info.labels it is treated as a data file ("Invalid mimetype"). Verified against
    # the live API, not assumed - a wrong shape uploads the images with no boxes
    # at all rather than failing loudly.
    labels = {
        "version": 1,
        "type": "bounding-box-labels",
        "boundingBoxes": {r["name"]: r["boxes"] for r in batch},
    }
    parts = [("bounding_boxes.labels", "application/json", json.dumps(labels).encode())]
    for rec in batch:
        with open(rec["path"], "rb") as fh:
            parts.append((rec["name"], _content_type(rec["name"]), fh.read()))
    boundary, body = _multipart(parts)
    # Order matters here - _parse_ingest_response zips this positionally against
    # the response's "files" array, which has no filename field to match on.
    sent_names = [rec["name"] for rec in batch]

    for attempt in range(MAX_RETRIES):
        req = urllib.request.Request(
            f"{INGEST}/{category}/files",
            data=body,
            method="POST",
            headers={
                "x-api-key": api_key,
                "x-disallow-duplicates": "1",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                raw = resp.read().decode()
            return _parse_ingest_response(raw, sent_names)
        except urllib.error.HTTPError as err:
            detail = err.read().decode()[:300]
            if err.code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES - 1:
                wait = 5 * 2**attempt
                print(f"    HTTP {err.code}, retrying in {wait}s")
                time.sleep(wait)
                continue
            return err.code, detail
        except urllib.error.URLError as err:
            if attempt < MAX_RETRIES - 1:
                wait = 5 * 2**attempt
                print(f"    {err.reason}, retrying in {wait}s")
                time.sleep(wait)
                continue
            return 0, str(err.reason)
    return 0, "exhausted retries"


def _ledger_path(project_id, slug):
    """Resume ledger, kept in the gitignored cache - not the committed manifest.

    Namespaced by project ID. These ledgers record what a *previous run already
    sent*, keyed by filename only - if a re-upload targets a different, empty
    project (as happened moving from 1094260 to 1097972), an un-namespaced ledger
    would mark every file "already uploaded" against a project that has never
    seen it, silently uploading nothing. The pre-namespacing ledger files
    (uploaded-<slug>.json, no project ID) are left on disk untouched as the
    historical record of what project 1094260 holds; they are simply never read
    again once every call site here passes a project ID.
    """
    return os.path.join(CACHE_DIR, f"uploaded-{project_id}-{slug}.json")


def _duplicates_ledger_path(project_id):
    """Cumulative, informational-only record of every file ever rejected server-side
    as an x-disallow-duplicates duplicate for this project, across runs. This is no
    longer read by reconcile_project_counts - dedupe_by_content now removes
    byte-identical images locally, before upload, so "expected" is correct without
    needing to know what the server rejected. Kept purely so a run can report how
    many server-side rejections it saw without re-deriving that from the log.
    Keyed by (label, category) -> list of filenames.
    """
    return os.path.join(CACHE_DIR, f"duplicates-{project_id}.json")


def load_duplicates_ledger(project_id):
    path = _duplicates_ledger_path(project_id)
    if not os.path.exists(path):
        return {}
    with open(path) as fh:
        return json.load(fh)


def save_duplicates_ledger(project_id, ledger):
    path = _duplicates_ledger_path(project_id)
    with open(path, "w") as fh:
        json.dump(ledger, fh, indent=1, sort_keys=True)
        fh.write("\n")


def upload_dataset(api_key, project_id, ds, records, live_categories=None):
    """Upload one class in batches, skipping anything already live.

    Returns (ok, failed, duplicates). A duplicate is a file the ingestion API
    rejected server-side (x-disallow-duplicates matched an existing sample) inside
    an otherwise-successful HTTP response - see _parse_ingest_response. It is
    marked done in the resume ledger (the content already exists in the project
    under some name, resending it would just reject again) but counted separately
    from a real upload so the reconciliation table can name it instead of hiding
    it inside a plain "uploaded" count the way the original bug did.

    "Pending" is decided against live_categories (sha256 -> category, ground
    truth fetched fresh from Edge Impulse this run) rather than the local
    filename-keyed ledger. The ledger alone is wrong for any source whose local
    files can be regenerated under a stable filename with different bytes -
    fetch_swg_camera_traps.py and make_pseudo_ir_vision.py both do this. Found
    29 Aug: swg-eurasian-wild-pig's ledger claimed 1800/1800 current filenames
    already sent, but 192 of their content hashes were not actually live -
    those 192 files' bytes had changed under the same name since whatever past
    run first populated the ledger, and the filename match hid it completely.
    live_categories is authoritative because it is what Edge Impulse itself
    reports right now, not a local record of what a past run believed it sent.
    The ledger is still written, for a human glancing at the cache without
    hitting the API, but it is no longer trusted to gate uploads.
    """
    live_categories = live_categories or {}
    path = _ledger_path(project_id, ds["slug"])
    done = set()
    if os.path.exists(path):
        with open(path) as fh:
            done = set(json.load(fh))
    pending = [r for r in records if r.get("_sha256") not in live_categories]
    stale_ledger = sum(1 for r in records if r["name"] in done and r.get("_sha256") not in live_categories)
    if stale_ledger:
        print(
            f"    NOTE: {stale_ledger} of {ds['label']}'s files are marked done in the local ledger "
            "by filename, but their current content is not actually live - re-sending them "
            "(a source file was likely regenerated with different bytes under the same name)"
        )
    if done:
        print(f"  resuming: {len(done)} already uploaded, {len(pending)} remaining")

    ok, failed, duplicates = 0, [], []
    for category in ("training", "testing"):
        subset = [r for r in pending if r["category"] == category]
        for i in range(0, len(subset), BATCH_SIZE):
            batch = subset[i : i + BATCH_SIZE]
            result = upload_batch(api_key, category, batch)
            if isinstance(result, tuple):
                failed.append((ds["label"], category, batch[0]["name"], result[0], result[1]))
                print(f"  [{category}] {ds['label']:8s} batch of {len(batch):3d} -> FAILED {result[0]}")
                continue
            accepted, rejected = result["accepted"], result["rejected"]
            ok += len(accepted)
            done.update(accepted)
            for name, reason in rejected:
                # The real x-disallow-duplicates rejection reads "An item with this
                # hash already exists (ids: ...)" - it never actually says
                # "duplicate" (confirmed via a live probe request), so matching only
                # on that word let every real duplicate fall through as a failure.
                if "already exists" in reason.lower() or "duplicate" in reason.lower():
                    duplicates.append((ds["label"], category, name, reason))
                    done.add(name)
                else:
                    failed.append((ds["label"], category, name, "rejected", reason))
            with open(path, "w") as fh:
                json.dump(sorted(done), fh)
            note = f", {len(rejected)} rejected" if rejected else ""
            print(
                f"  [{category}] {ds['label']:8s} batch of {len(batch):3d} -> "
                f"{len(accepted)} uploaded{note} ({ok} so far)"
            )
    return ok, failed, duplicates


def write_manifest(entries):
    """Commit the split assignment so the reported number is reproducible from a clone."""
    os.makedirs(os.path.dirname(MANIFEST), exist_ok=True)
    doc = {"split_seed": SPLIT_SEED, "test_fraction": TEST_FRACTION, "classes": entries}
    with open(MANIFEST, "w") as fh:
        json.dump(doc, fh, indent=1)
        fh.write("\n")
    print(f"\nWrote split ledger -> {MANIFEST}")


def _count_samples(project_id, api_key, category, label=None):
    """How many samples Edge Impulse actually stored, straight from the project - not
    what this run parsed or sent. GET /{project}/raw-data/count, confirmed live
    against the Studio API (countSamples in the published OpenAPI spec).

    label=None omits the labels filter entirely and counts every sample in the
    category regardless of what boxes it carries - see reconcile_project_counts
    for why that, not a per-label count, is the number that must be hard-failed
    on.
    """
    params = {"category": category}
    if label is not None:
        params["labels"] = json.dumps([label])
    query = urllib.parse.urlencode(params)
    data = _request(f"{STUDIO}/{project_id}/raw-data/count?{query}", api_key=api_key)
    return data["count"]


def fetch_live_content_categories(project_id, api_key):
    """Ground truth for what category each already-stored image actually holds
    in Edge Impulse right now, keyed by sha256 content hash - not what any local
    recomputation thinks it should be.

    Root cause this closes (found live, 29 Aug, via a hard reconciliation
    failure - Elephant training off by 680, Boar carrying 136 more live images
    than the manifest expected): split_by_group's seeded shuffle is deterministic
    given an *identical* input group list, but its output is not stable under
    insertion or removal - adding or dropping even one group from a dataset (a
    new source landing, a contamination fix pulling images out) changes the
    length/content of the list random.Random(SPLIT_SEED).shuffle() consumes,
    which can move the computed category of *every other* group in that dataset,
    not just the one that changed. Edge Impulse itself never moves an
    already-uploaded sample's category on a re-run (content-hash dedup just skips
    re-sending it), so each fresh recomputation silently drifted further from
    what is actually live - exactly the shape of the failure that surfaced this.

    The fix is to stop trusting recomputation for anything already stored: ask
    Edge Impulse directly what category each piece of content already has, and
    let split_by_group lock those groups to their live category instead of
    reshuffling them. Only genuinely new content (never seen live before) goes
    through the seeded shuffle at all. This makes the split append-only and
    self-healing regardless of how many more sources get added later - see
    split_by_group's own docstring for the locking logic.

    Paginates GET /{project}/raw-data (listSamples), 1000 per page, no category
    filter - a sample's own "category" field is read directly from each row
    rather than filtering by it, so this is exactly one full pass over the
    project regardless of how many categories exist.
    """
    print("\nFetching live content-hash -> category map from the project (ground truth for the split)...")
    by_hash = {}
    offset = 0
    page_size = 1000
    while True:
        # category is a required query param (confirmed live: omitting it returns
        # {"success": false, "error": "Unknown category undefined"}, not all rows).
        # "all" is a real enum value per the OpenAPI spec's RawDataFilterCategory
        # and returns every category in one paginated pass.
        params = urllib.parse.urlencode({"limit": page_size, "offset": offset, "category": "all"})
        data = _request(f"{STUDIO}/{project_id}/raw-data?{params}", api_key=api_key)
        samples = data.get("samples", [])
        if not samples:
            break
        for s in samples:
            digest = s.get("sha256Hash")
            category = s.get("category")
            if not digest or not category:
                continue
            prior = by_hash.get(digest)
            if prior is not None and prior != category:
                print(
                    f"    NOTE: content hash {digest[:12]}... is stored under both "
                    f"'{prior}' and '{category}' live (sample id {s.get('id')}) - "
                    "keeping the first one seen, flagging for manual look"
                )
                continue
            by_hash[digest] = category
        offset += len(samples)
        if len(samples) < page_size:
            break
    print(f"  {len(by_hash)} distinct stored content hashes found live across the project")
    return by_hash


def reconcile_project_counts(project_id, api_key, manifest):
    """Hard-fail if the project doesn't actually hold what the manifest expects.

    The old reconciliation table only ever compared *parsed* counts to *sent*
    counts - both numbers this same process just computed - so it could never
    catch a gap between "sent" and "actually stored". That is precisely how the
    71-image shortfall in ml/vision/README.md went unnoticed with "0 failures"
    printed.

    A first version of this function queried raw-data/count with a per-class
    labels=[...] filter and hard-failed on that. That undercounts on its own:
    Edge Impulse's per-label count only counts samples carrying >=1 box of that
    label, so a class's own background (zero-box) images - uploaded correctly,
    with an intentionally empty boundingBoxes list per parse_coco's docstring -
    are invisible to it. Elephant alone carries 552 such background images,
    which turned a real 71-image structural gap into an apparent ~627-image one
    the first time this ran. The number that actually reflects upload success is
    the TOTAL per-category count with no labels filter, compared against the sum
    of every class's expected count for that category - that comparison is
    immune to the background-image blind spot.

    A second version hard-failed on ~71 genuine byte-identical duplicate images
    that were never actually a lost sample - x-disallow-duplicates correctly
    collapsed them, but "expected" was still counting each duplicate filename as
    if it would land as its own sample. A third version tried to patch this by
    subtracting server-reported duplicate rejections from "expected" after the
    fact; that broke worse, because a forced re-verify of already-uploaded files
    reports "already exists" for every single one of them (matching their own
    prior upload, not a sibling), and that self-match is indistinguishable from a
    genuine cross-file duplicate once it's only seen as a rejection reason string.

    The real fix lives upstream, in dedupe_by_content (SHA1, applied before the
    split is computed, shared across every source for a label) - it drops
    byte-identical images before they are ever counted as "expected" at all, so
    this function no longer needs to know anything about duplicates. What it
    compares here is exactly what the corpus, after local dedup, should be able
    to store - a genuine mismatch at this point means a real upload failure, not
    an accounted-for duplicate.
    """
    print("\nProject-level reconciliation (queried from Edge Impulse, not from this run's own counters):")
    for label in sorted(manifest):
        entry = manifest[label]
        for category in ("training", "testing"):
            expected = len(entry[category])
            actual = _count_samples(project_id, api_key, category, label)
            print(f"  {label:10s} {category:9s} expected {expected:5d}  actual {actual:5d}  (per-label, informational)")

    mismatch = False
    for category in ("training", "testing"):
        expected_total = sum(len(manifest[label][category]) for label in manifest)
        actual_total = _count_samples(project_id, api_key, category)
        flag = "" if actual_total == expected_total else "  <-- MISMATCH"
        print(f"  {'TOTAL':10s} {category:9s} expected {expected_total:5d}  actual {actual_total:5d}{flag}")
        if actual_total != expected_total:
            mismatch = True
    if mismatch:
        print(
            "\nHARD FAIL: the project does not hold the number of samples this run expects, by total "
            "count (not per-label - see this function's docstring for why per-label undercounts), "
            "even after local content-hash dedup. Do not train against this project until this is "
            "understood and recorded."
        )
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="do everything except upload")
    ap.add_argument("--limit", type=int, help="use only the first N images per class")
    args = ap.parse_args()

    api_key = os.environ.get("EI_API_KEY")
    project_id = os.environ.get("EI_PROJECT_ID")
    # RF_API_KEY matches secrets/vision_pipeline.env.example; ROBOFLOW_API_KEY kept as a
    # fallback for anyone with the old name already exported.
    rf_key = os.environ.get("RF_API_KEY") or os.environ.get("ROBOFLOW_API_KEY")
    if not api_key or not project_id or not rf_key:
        print(
            "Set EI_API_KEY, EI_PROJECT_ID and RF_API_KEY environment variables first.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not args.dry_run:
        ensure_object_detection(project_id, api_key)

    # Always fetched, dry-run included - a dry-run's whole purpose is an accurate
    # preview, and "how many groups are new vs. already-locked" is exactly the kind
    # of thing that must not differ between the preview and the real run. Read-only
    # call, safe against an empty project (nothing comes back, everything treated
    # as new, which is correct for a first-ever run).
    live_categories = fetch_live_content_categories(project_id, api_key)

    all_failed, all_duplicates, manifest, report_rows = [], [], {}, []
    content_seen = {}
    # Loaded once, up front, so the per-dataset loop below can drop a record whose
    # filename was already confirmed a server-side duplicate in some PAST run -
    # see the cross-run gap this closes, dated 28 Aug, in reconcile_project_counts's
    # docstring below the "third version" paragraph.
    duplicates_ledger = load_duplicates_ledger(project_id)
    for ds in DATASETS:
        origin = f"{ds['workspace']}/{ds['project']} v{ds['version']}" if ds.get("workspace") else ds["slug"]
        tag = " [SYNTHETIC]" if ds.get("synthetic") else ""
        print(f"\n=== {ds['label']}: {origin} ({ds['license']}){tag} ===")
        root = fetch_dataset(ds, rf_key)
        records, drops, background = parse_coco(root, ds)
        # Hashed here, immediately after parsing, so every downstream stage that
        # can drop or reorder records - group_caps, sample_by_group, dedupe_by_content,
        # split_by_group - has content hashes available to check against what's
        # already live. sample_by_group used to run before this was computed at all,
        # which is exactly why its own seeded shuffle had the same silent-drift bug
        # as split_by_group (see sample_by_group's docstring) and went unnoticed for
        # longer: nothing downstream of it could tell a "new" selection from a stale one.
        for rec in records:
            rec["_sha256"] = _sha256(rec["path"])
        boxes = sum(len(r["boxes"]) for r in records)
        labelled = len(records) - background
        print(f"  parsed {len(records)} images / {boxes} boxes")
        print(f"    {labelled} carry >=1 box, {background} are background (zero boxes, kept)")
        if ds["expect_images"] is None:
            # A local_root source has no third-party "page" to cross-check against -
            # its own producing script's real, printed selection count is the only
            # expectation there is, and it is trusted as-is rather than faked here.
            # Must add back every image-level filter drop, not just missing_file -
            # records already excludes species/broadcast/visually-contaminated
            # images, so leaving those out here made the gap check below subtract
            # them a second time and print a false negative "UNEXPLAINED GAP"
            # (caught 28 Aug when pseudo-ir-elephant got its first real tv_broadcast
            # drops: 233 parsed - 233 baseline - 17 drop = -17, though nothing was
            # actually missing).
            ds = dict(
                ds,
                expect_images=(
                    len(records)
                    + drops["missing_file"]
                    + drops["species_contaminated"]
                    + drops["visually_contaminated"]
                    + drops["tv_broadcast"]
                    + drops["generic_named_scrape"]
                    + drops["unreliable_zero_box"]
                ),
            )
            print("    local source: no page count to cross-check, expect_images set to parsed count")
        else:
            print(f"    project page reports {ds['expect_images']} images / {ds['page_boxes']} boxes")
            if ds["page_boxes"] is not None and boxes != ds["page_boxes"]:
                print(
                    f"    NOTE: export carries {boxes} boxes, page says {ds['page_boxes']} - the page "
                    f"tallies the project's live label state, this frozen export is what is uploaded"
                )
        for reason, count in drops.items():
            if count:
                print(f"    dropped {count} ({reason})")
        gap = (
            ds["expect_images"]
            - len(records)
            - drops["missing_file"]
            - drops["species_contaminated"]
            - drops["visually_contaminated"]
            - drops["tv_broadcast"]
            - drops["generic_named_scrape"]
            - drops["unreliable_zero_box"]
        )
        if gap:
            print(f"    UNEXPLAINED GAP: {gap} images unaccounted for - do not trust these counts")

        for group_name, cap in ds.get("group_caps", {}).items():
            records = cap_named_group(records, group_name, cap, ds["label"])
            boxes = sum(len(r["boxes"]) for r in records)
            background = sum(1 for r in records if not r["boxes"])
            labelled = len(records) - background
            print(
                f"    post-cap: {len(records)} images / {boxes} boxes "
                f"({labelled} boxed, {background} background)"
            )

        if ds.get("sample_target"):
            records = sample_by_group(records, ds["sample_target"], ds["label"], live_categories)
            boxes = sum(len(r["boxes"]) for r in records)
            background = sum(1 for r in records if not r["boxes"])
            labelled = len(records) - background
            print(
                f"    post-sample: {len(records)} images / {boxes} boxes "
                f"({labelled} boxed, {background} background)"
            )

        records, content_dupes = dedupe_by_content(records, ds["label"], content_seen)
        if content_dupes:
            boxes = sum(len(r["boxes"]) for r in records)
            background = sum(1 for r in records if not r["boxes"])
            print(
                f"    dropped {len(content_dupes)} (content_duplicate: byte-identical to an "
                f"earlier {ds['label']} image, possibly from a different source)"
            )
            for name, prior in content_dupes[:5]:
                print(f"      {name} == {prior}")
            if len(content_dupes) > 5:
                print(f"      ... and {len(content_dupes) - 5} more")

        groups, clustered = split_by_group(records, ds["label"], live_categories)
        if args.limit:
            records = records[: args.limit]
            print(f"    --limit {args.limit}: truncated to {len(records)} images")

        entry = {
            "source": f"{ds['workspace']}/{ds['project']}/{ds['version']}" if ds.get("workspace") else ds["slug"],
            "license": ds["license"],
            "synthetic": ds.get("synthetic", False),
            "relabelled_from": ds["rename"] or None,
            "dropped_classes": sorted(ds["drop"]) or None,
            "images": len(records),
            "images_with_boxes": labelled,
            "background_images": background,
            "boxes": boxes,
            "groups": len(groups),
            "images_in_multi_image_groups": clustered,
            "drops": drops,
            "training": sorted(r["name"] for r in records if r["category"] == "training"),
            "testing": sorted(r["name"] for r in records if r["category"] == "testing"),
        }
        # A label (e.g. "Boar") can now come from more than one source - merge into
        # a combined entry with a per-source breakdown, rather than overwrite.
        if ds["label"] in manifest:
            prior = manifest[ds["label"]]
            sources = prior.get("sources") or [
                {k: v for k, v in prior.items() if k not in ("training", "testing")}
            ]
            sources.append({k: v for k, v in entry.items() if k not in ("training", "testing")})
            manifest[ds["label"]] = {
                "sources": sources,
                "images": prior["images"] + entry["images"],
                "images_with_boxes": prior["images_with_boxes"] + entry["images_with_boxes"],
                "background_images": prior["background_images"] + entry["background_images"],
                "boxes": prior["boxes"] + entry["boxes"],
                "groups": prior["groups"] + entry["groups"],
                "images_in_multi_image_groups": (
                    prior["images_in_multi_image_groups"] + entry["images_in_multi_image_groups"]
                ),
                # Real vs synthetic must stay separable at the combined level, not
                # just per-source - see the plan's Phase 4 requirement that a
                # synthetic count is "never folded into a real data total silently".
                # prior["real_images"]/["synthetic_images"] always exist - both the
                # else branch below and every earlier pass through this branch set
                # them.
                "real_images": prior["real_images"] + (0 if entry["synthetic"] else entry["images"]),
                "synthetic_images": prior["synthetic_images"] + (entry["images"] if entry["synthetic"] else 0),
                "training": sorted(prior["training"] + entry["training"]),
                "testing": sorted(prior["testing"] + entry["testing"]),
            }
        else:
            manifest[ds["label"]] = dict(
                entry,
                real_images=0 if entry["synthetic"] else entry["images"],
                synthetic_images=entry["images"] if entry["synthetic"] else 0,
            )

        row = {
            "label": ds["label"],
            "slug": ds["slug"],
            "expect_images": ds["expect_images"],
            "images": entry["images"],
            "images_with_boxes": entry["images_with_boxes"],
            "background_images": entry["background_images"],
            "train": len(entry["training"]),
            "test": len(entry["testing"]),
            "uploaded": 0,
            "synthetic": entry["synthetic"],
        }
        if args.dry_run:
            print(f"  --dry-run: not uploading {len(records)} images")
            report_rows.append(row)
            continue
        ok, failed, duplicates = upload_dataset(api_key, project_id, ds, records, live_categories)
        all_failed.extend(failed)
        all_duplicates.extend(duplicates)
        row["uploaded"] = ok
        row["duplicates"] = len(duplicates)
        report_rows.append(row)

    if args.limit:
        print(
            f"\n--limit {args.limit}: NOT writing {MANIFEST} - a limited run's manifest "
            f"doesn't reflect the real dataset and must never overwrite the committed one"
        )
    else:
        write_manifest(manifest)

    print("\nReconciliation (source -> uploaded, every drop named above):")
    header = f"  {'class':10s} {'slug':>26s} {'source':>7s} {'parsed':>7s} {'boxed':>7s} {'bkgnd':>7s}"
    print(f"{header} {'train':>7s} {'test':>7s} {'uploaded':>9s} {'dupes':>7s}")
    for row in report_rows:
        mark = "  [SYNTHETIC]" if row["synthetic"] else ""
        print(
            f"  {row['label']:10s} {row['slug']:>26s} {row['expect_images']:7d} {row['images']:7d} "
            f"{row['images_with_boxes']:7d} {row['background_images']:7d} "
            f"{row['train']:7d} {row['test']:7d} {row['uploaded']:9d} {row.get('duplicates', 0):7d}{mark}"
        )
    for label in sorted({r["label"] for r in report_rows}):
        real = sum(r["images"] for r in report_rows if r["label"] == label and not r["synthetic"])
        synthetic = sum(r["images"] for r in report_rows if r["label"] == label and r["synthetic"])
        note = f" ({real} real + {synthetic} synthetic)" if synthetic else ""
        print(f"  {label} combined total: {real + synthetic} images{note}")

    if all_duplicates:
        print(
            f"\nDuplicates ({len(all_duplicates)} files the ingestion API rejected server-side, "
            f"HTTP status 200 but individually unaccepted - x-disallow-duplicates matched an "
            f"existing sample):"
        )
        for d in all_duplicates:
            print(" ", d)

    if not args.dry_run and not args.limit:
        # Reuses the copy loaded up front for the cross_run_duplicate filter above -
        # nothing in this run writes to the on-disk ledger before this point, so a
        # second read here would only be a redundant, identical re-read.
        before = sum(len(v) for cats in duplicates_ledger.values() for v in cats.values())
        for label, category, name, _reason in all_duplicates:
            bucket = duplicates_ledger.setdefault(label, {}).setdefault(category, [])
            if name not in bucket:
                bucket.append(name)
        after = sum(len(v) for cats in duplicates_ledger.values() for v in cats.values())
        if after != before:
            save_duplicates_ledger(project_id, duplicates_ledger)
            print(f"\nDuplicates ledger updated: {before} -> {after} confirmed duplicates on record (informational only)")

    exit_code = 0
    if all_failed:
        print("\nFailures:")
        for f in all_failed:
            print(" ", f)
        exit_code = 1

    if not args.dry_run:
        exit_code = max(exit_code, reconcile_project_counts(project_id, api_key, manifest))

    if exit_code:
        sys.exit(exit_code)

    if not args.dry_run:
        print(
            f"\nCheck the result at "
            f"https://studio.edgeimpulse.com/studio/{project_id}/acquisition/training"
        )


if __name__ == "__main__":
    main()
