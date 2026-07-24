"""
Runtime calibration applier (cross-platform, no hard-coded paths).

Loads a calibration produced by calibrate.py (calibration.json) and applies the
SAME correction to new raw images that share the fixed camera framing:

    undistort(K, dist)  ->  warpPerspective(H, output_size)

The camera framing is constant, so the calibration is computed once (offline) and
reused for every image here. This module does NOT re-run calibration.

Usage
-----
    # single file
    python apply_calibration.py --calib calibration.json --input frame.jpeg --output out/

    # whole folder
    python apply_calibration.py --calib calibration.json --input raw_dir/ --output out/

Or import and use the class from a watcher/service:

    from apply_calibration import Calibrator
    cal = Calibrator("calibration.json")
    cal.apply_file("frame.jpeg", "out/")          # -> out/frame_calibrated.png
"""
import argparse
import json
import os
import cv2
import numpy as np

IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff")


class Calibrator:
    def __init__(self, calib_path):
        with open(calib_path, "r", encoding="utf-8") as fp:
            c = json.load(fp)
        self.K = np.array(c["camera_matrix"], dtype=np.float64)
        self.dist = np.array(c["dist_coeffs"], dtype=np.float64)
        self.H = np.array(c["homography_undistorted_to_calibrated"], dtype=np.float64)
        self.out_w, self.out_h = int(c["output_size"][0]), int(c["output_size"][1])
        self.mm_per_px = c.get("mm_per_px")
        self._maps = {}  # (w, h) -> (mapx, mapy), built lazily and cached

    def _maps_for(self, w, h):
        key = (w, h)
        if key not in self._maps:
            self._maps[key] = cv2.initUndistortRectifyMap(
                self.K, self.dist, None, self.K, (w, h), cv2.CV_32FC1)
        return self._maps[key]

    def apply(self, img):
        """Apply undistort + homography to an image (grayscale or color)."""
        h, w = img.shape[:2]
        mapx, mapy = self._maps_for(w, h)
        und = cv2.remap(img, mapx, mapy, cv2.INTER_CUBIC)
        return cv2.warpPerspective(und, self.H, (self.out_w, self.out_h),
                                   flags=cv2.INTER_CUBIC, borderValue=0)

    def apply_file(self, in_path, out_dir, suffix="_calibrated"):
        """Read one image, apply, write PNG to out_dir. Returns output path."""
        img = cv2.imread(in_path, cv2.IMREAD_UNCHANGED)
        if img is None:
            raise ValueError(f"could not read image: {in_path}")
        out = self.apply(img)
        os.makedirs(out_dir, exist_ok=True)
        stem = os.path.splitext(os.path.basename(in_path))[0]
        out_path = os.path.join(out_dir, f"{stem}{suffix}.png")
        if not cv2.imwrite(out_path, out):
            raise IOError(f"could not write output: {out_path}")
        return out_path


def main():
    ap = argparse.ArgumentParser(description="Apply a saved calibration to raw image(s).")
    ap.add_argument("--calib", required=True, help="path to calibration.json")
    ap.add_argument("--input", required=True, help="image file or directory of images")
    ap.add_argument("--output", required=True, help="output directory")
    ap.add_argument("--suffix", default="_calibrated", help="output filename suffix")
    args = ap.parse_args()

    cal = Calibrator(args.calib)

    if os.path.isdir(args.input):
        files = sorted(f for f in os.listdir(args.input)
                       if f.lower().endswith(IMG_EXTS))
        if not files:
            print(f"no images found in {args.input}")
            return
        for f in files:
            out = cal.apply_file(os.path.join(args.input, f), args.output, args.suffix)
            print(f"{f} -> {out}")
    else:
        out = cal.apply_file(args.input, args.output, args.suffix)
        print(f"{args.input} -> {out}")


if __name__ == "__main__":
    main()
