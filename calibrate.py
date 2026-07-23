"""
Powder-bed image calibration via checkerboard perspective rectification.

Uses the Zivid CB02 checkerboard (5x5 interior corners, 20 mm pitch) to compute a
plane homography that maps the camera view to a metric, top-down (fronto-parallel)
view. The same homography is applied to the raw powder-bed images so distances are
consistent and measurable (known mm/pixel scale).

Note: a single checkerboard image only supports perspective/scale rectification of
the board plane. It does NOT estimate lens distortion (that needs many views).
"""
import cv2, numpy as np, json, os

BASE = r"C:\Users\hyang\Desktop\Image_calibration"
CHECKER = os.path.join(BASE, "Checker", "SI0201437020260723044428_00001_000_040_AfterRecoating.jpg")
RAW_DIR = os.path.join(BASE, "Raw_image")
OUT_DIR = os.path.join(BASE, "Calibrated_image")
os.makedirs(OUT_DIR, exist_ok=True)

PATTERN = (5, 5)      # interior corners
SQUARE_MM = 20.0      # checker pitch
PX_PER_MM = 3.1       # output scale (~native board resolution, keeps detail)

# ---- 1. detect checkerboard corners ------------------------------------------
checker_gray = cv2.imread(CHECKER, cv2.IMREAD_GRAYSCALE)
found, corners = cv2.findChessboardCornersSB(checker_gray, PATTERN, cv2.CALIB_CB_NORMALIZE_IMAGE)
if not found:
    raise SystemExit("Checkerboard not detected")
corners = corners.reshape(-1, 2).astype(np.float32)

# ---- 2. metric homography (image px -> rectified px) -------------------------
obj = np.array([[c * SQUARE_MM, r * SQUARE_MM]
                for r in range(PATTERN[1]) for c in range(PATTERN[0])], np.float32)
obj_px = obj * PX_PER_MM
H0, _ = cv2.findHomography(corners, obj_px, cv2.RANSAC)

proj = cv2.perspectiveTransform(corners.reshape(-1, 1, 2), H0).reshape(-1, 2)
err = np.linalg.norm(proj - obj_px, axis=1)

# ---- 3. size output canvas so the whole warped frame fits --------------------
h, w = checker_gray.shape
img_corners = np.array([[0, 0], [w, 0], [w, h], [0, h]], np.float32).reshape(-1, 1, 2)
mapped = cv2.perspectiveTransform(img_corners, H0).reshape(-1, 2)
xmin, ymin = np.floor(mapped.min(0)); xmax, ymax = np.ceil(mapped.max(0))
T = np.array([[1, 0, -xmin], [0, 1, -ymin], [0, 0, 1]], np.float64)
H = T @ H0
out_w, out_h = int(xmax - xmin), int(ymax - ymin)

print(f"corners detected : {len(corners)}  ({PATTERN[0]}x{PATTERN[1]})")
print(f"reproj error px  : mean {err.mean():.2f}  max {err.max():.2f}")
print(f"scale            : {PX_PER_MM} px/mm  ->  {1/PX_PER_MM:.4f} mm/px")
print(f"output canvas    : {out_w} x {out_h}")

def rectify(gray_or_bgr):
    return cv2.warpPerspective(gray_or_bgr, H, (out_w, out_h),
                               flags=cv2.INTER_CUBIC, borderValue=0)

# ---- 4. apply to raw images --------------------------------------------------
raw_files = [f for f in os.listdir(RAW_DIR) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
for f in raw_files:
    img = cv2.imread(os.path.join(RAW_DIR, f), cv2.IMREAD_UNCHANGED)
    rect = rectify(img)
    name = os.path.splitext(f)[0] + "_calibrated.png"
    cv2.imwrite(os.path.join(OUT_DIR, name), rect)
    print(f"saved            : Calibrated_image/{name}")

# ---- 5. verification artifacts ----------------------------------------------
# rectified checker with a 20 mm metric grid overlay (lines should be straight/even)
checker_rect = cv2.cvtColor(rectify(checker_gray), cv2.COLOR_GRAY2BGR)
step = int(round(SQUARE_MM * PX_PER_MM))
for x in range(0, out_w, step):
    cv2.line(checker_rect, (x, 0), (x, out_h), (0, 180, 0), 1)
for y in range(0, out_h, step):
    cv2.line(checker_rect, (0, y), (out_w, y), (0, 180, 0), 1)
cv2.imwrite(os.path.join(OUT_DIR, "_checker_calibrated_gridoverlay.png"), checker_rect)

# detected corners on original
vis = cv2.cvtColor(checker_gray, cv2.COLOR_GRAY2BGR)
cv2.drawChessboardCorners(vis, PATTERN, corners.reshape(-1, 1, 2), found)
cv2.imwrite(os.path.join(OUT_DIR, "_checker_corners_detected.png"), vis)

# ---- 6. persist calibration for reuse ---------------------------------------
with open(os.path.join(OUT_DIR, "calibration.json"), "w") as fp:
    json.dump({
        "pattern_interior_corners": PATTERN,
        "square_mm": SQUARE_MM,
        "px_per_mm": PX_PER_MM,
        "mm_per_px": 1 / PX_PER_MM,
        "homography": H.tolist(),
        "output_size": [out_w, out_h],
        "reproj_error_px_mean": float(err.mean()),
        "reproj_error_px_max": float(err.max()),
        "note": "H maps original-image pixels -> calibrated top-down pixels."
    }, fp, indent=2)
print("saved            : Calibrated_image/calibration.json (+ 2 verification images)")
