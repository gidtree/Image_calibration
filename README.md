# Image Calibration — Powder Bed Rectification

체커보드(Zivid CB02, 20 mm 간격)를 이용해 금속 3D 프린팅(LPBF) 파우더 베드 카메라 이미지의
**렌즈 왜곡 + 원근 왜곡**을 보정하고, 실측 스케일(mm/px)이 부여된 top-down 뷰로 변환합니다.
보정 정확도는 **작업영역(반짝이는 베드)** 에 맞춰 최적화되어 있습니다.

## 구조
```
Image_calibration/
├── calibrate.py          # 캘리브레이션 파이프라인
├── Checker/              # 체커보드 캘리브레이션 이미지 (작업영역 네 모서리 + 중앙)
├── Raw_image/            # 원본 파우더 베드 이미지
└── Calibrated_image/     # 보정 결과 + calibration.json
```

## 사용법
```bash
pip install opencv-python numpy
python calibrate.py
```

## 처리 파이프라인 (undistort → homography)
1. 모든 체커보드에서 내부 코너 검출 (`findChessboardCornersSB`)
2. **렌즈 왜곡 보정** — 반경 왜곡 1항 `k1`만 추정(principal point는 중앙 고정)해 undistort
3. **원근 보정** — undistort된 기준 보드로 실측 20 mm 격자 호모그래피 계산
4. raw 이미지에 `undistort → warpPerspective` 적용 → `Calibrated_image/`에 저장

- 스케일: 0.3226 mm/px (3.1 px/mm)
- 왜곡계수: `k1 ≈ -0.185` (완만한 배럴)

## 왜 k1만 쓰는가 (모델 선택 근거)
체커보드 6장이 모두 베드 위에 **평평하게(동일 자세로)** 놓여 있어 전체 내부 파라미터 solve는
기하학적으로 degenerate합니다(무제약 캘리브레이션은 `k3≈+5.9`, `fx≠fy` 같은 발산값을 냄).

대신 보드가 **작업영역의 네 모서리 + 중앙**을 샘플링했다는 점을 활용해, **leave-one-out
교차검증**으로 작업영역 안에서 일반화되는 최소 모델을 골랐습니다.

| 모델 | held-out 코너 보드 잔차 | 판정 |
|---|---|---|
| 호모그래피만 | ~0.17 px | 기준 |
| **k1 (반경 1항)** | **~0.09 px** | ✅ 채택 (과적합 없이 개선) |
| k1, k2 | ~0.10 px | k2 이득 없음 |
| k1, k2 + free pp | 일부 0.31 px | ❌ 과적합 |

→ `k1`만으로 작업영역 네 모서리 잔차가 약 절반으로 줄고 held-out에서도 개선됩니다. 왜곡이 큰
화면 **주변부(작업영역 밖)** 는 데이터가 없어 외삽되지만, 해당 영역은 관심 대상이 아니므로 무방합니다.
`calibration.json`의 `work_area_polygon_calibrated_px` 가 정확도가 검증된 영역입니다.

## 전체 프레임까지 보정하려면 (향후 촬영 가이드)
작업영역 밖(화면 전체)까지 정확히 보정하려면 아래처럼 촬영해 재실행하세요.
- 보드를 **다양한 각도로 기울여** 촬영 (앞/뒤/좌/우로 약 20~45°)
- 보드가 **화면 네 모서리·가장자리까지** 닿도록 위치를 바꿔가며 촬영
- 총 **10~15장** 확보 → `calibrate.py`의 `flags`를 완화해 K + (k1,k2,p1,p2) 추정
