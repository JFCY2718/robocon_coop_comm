# AprilTag dynamic six-LED vision

## Scope and safety boundary

The optional dynamic mode locates the R1 beacon board with AprilTag ID 0 and
projects six circular sampling regions into the current image. It produces a
bitmask, confidence and structured validity reason. It does not command motors
or bypass the R2 mission state machine.

The original fixed ROI mode remains the default:

```text
--roi-mode fixed      existing click/ROI-file workflow
--roi-mode apriltag   tag-guided dynamic ROI workflow
```

For the recommended competition settings, use `--competition`. It enables
AprilTag auto ROI, percentile/background-ring decoding, threshold hysteresis,
periodic optical-flow tracking, newest-frame acquisition and temporal protocol
validation. See `R2_VISION_COMPETITION_UPGRADE.md`.

The LED order remains exactly:

```text
D0, D1, D2, D3, REF, PAR
bit0                 bit5
```

## Physical model

- Board front face: 280 x 220 mm, front-view centre is the origin. The drawing
  does not specify the board thickness.
- Board X points right, Y points up, and all centres use Z=0.
- AprilTag family/ID: `tag36h11`, ID 0.
- AprilTag detection edge: 150.0 mm. This must be the detected black outer
  edge; if the physical 150 mm includes a white border, measure and configure
  the black edge instead.
- Tag top-left is 10 mm from the board left edge and 35 mm from the top edge.
- Tag centre on board: `(-55, 0)` mm.
- LED centres on board:
  - D0 `(40, 70)`, D1 `(80, 70)`, D2 `(120, 70)` mm.
  - D3 `(40, 20)`, REF `(80, 20)`, PAR `(120, 20)` mm.
- Lamp face diameter: 22.40 mm; default sample radius is 65 percent of its
  11.20 mm radius, or 7.28 mm.

The built-in model is in `beacon_geometry.py`. A JSON file passed through
`--beacon-layout` may override measured dimensions. It must preserve the six
LED names and order. `--tag-size` is in metres; geometry JSON dimensions are in
millimetres.

## Processing pipeline

```text
Hikrobot or offline frame
  -> lazy pupil-apriltags detection
  -> ID, hamming and decision-margin gates
  -> planar homography from the black tag corners
  -> six projected centres and scale-dependent circular radii
  -> explicit bounds validation
  -> existing SixLedRoiDecoder threshold/confidence logic
  -> REF and even-parity validation
  -> state_id 0..15 and structured validity metadata
```

The last projected ROIs may remain visible for at most `--tag-lost-frames` to
help diagnosis. Any frame without a current valid tag is immediately marked
`valid=false`; stale regions are never actionable.

## Optional pose calibration

Pose is disabled unless both `--camera-calibration` and `--pose` are supplied.
The JSON format is:

```json
{
  "image_width": 1920,
  "image_height": 1200,
  "camera_matrix": [
    [1000.0, 0.0, 960.0],
    [0.0, 1000.0, 600.0],
    [0.0, 0.0, 1.0]
  ],
  "dist_coeffs": [0.0, 0.0, 0.0, 0.0, 0.0]
}
```

These numbers illustrate the file shape only. Never use them as real Hikrobot
intrinsics. The current pose output is tag-to-camera pose from pupil-apriltags;
camera-to-R2 extrinsics remain a separate, unimplemented interface.

## Ubuntu installation and live command

```bash
cd /home/jfcy/rc/robocon_coop_comm
source .venv/bin/activate
python3 -m pip install -e '.[vision,apriltag]'

export MVCAM_COMMON_RUNENV=/opt/MVS/lib
export PYTHONPATH=/opt/MVS/Samples/64/Python/MvImport:$PYTHONPATH
export LD_LIBRARY_PATH=/opt/MVS/lib/64:/opt/MVS/bin:$LD_LIBRARY_PATH

python3 tools/hikrobot_6led_live.py \
  --roi-mode apriltag \
  --tag-family tag36h11 --tag-id 0 --tag-size 0.150 \
  --tag-min-margin 30 --tag-max-hamming 0 \
  --roi-radius-scale 0.65 --tag-lost-frames 5 \
  --threshold 60 --exposure 8000 --gain 0 --timeout 5000 \
  --draw-tag --draw-dynamic-rois --protocol \
  --log data/sixled/logs/apriltag_site.csv
```

Offline decoding does not import or initialize the MVS SDK:

```bash
python3 tools/hikrobot_6led_live.py \
  --image sample.jpg --roi-mode apriltag \
  --draw-tag --draw-dynamic-rois \
  --output-image /tmp/apriltag_sixled_debug.jpg
```

## Field validation

1. Print tag36h11 ID 0 and measure the detected black outer edge; pass the
   measured value through `--tag-size` if it is not 150.0 mm.
2. Mount the tag flat and matte with its 150 x 150 mm detection square at the
   drawing position: left/top offsets 10/35 mm and centre `(-55, 0)` mm.
3. Verify tag-only detection at 1 m, 3 m and the expected maximum distance.
   Record tag edge pixels and decision margin; about 60 pixels at maximum
   distance is the initial target, not an acceptance claim.
4. Illuminate the six lamps and check that every dynamic circle stays inside
   the lamp cap during translation, rotation and distance changes.
5. Test all-off, all-on, every single bit and representative combinations.
6. Cover the tag and confirm output becomes invalid immediately and stale debug
   ROIs disappear after the configured frame count.
7. Save a log, then run `python3 tools/sixled_log_summary.py <log>`.
8. Only after optical validation, feed valid events through R2 local safety
   guards and its mission state machine.

Still required from the physical system: measured tag size, real intrinsics,
lens/distortion choice, camera-to-R2 extrinsics, exposure/gain/threshold,
decision-margin distribution, ROI radius scale, motion blur results, and
maximum reliable distance. Unit tests and offline images do not replace these
measurements.

The legacy built-in board remains 280 x 220 mm for compatibility. New builds
should pass `data/sixled/configs/competition_beacon_320x240.json` to use the
recommended 320 x 240 mm carrier without silently changing an existing board.
