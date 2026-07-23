# Image Calibration — Powder Bed Rectification

체커보드(Zivid CB02, 5×5 내부 코너, 20 mm 간격)를 이용해 금속 3D 프린팅(LPBF) 파우더 베드
카메라 이미지의 원근 왜곡을 보정하고, 실측 스케일(mm/px)이 부여된 top-down 뷰로 변환합니다.

## 구조
```
Image_calibration/
├── calibrate.py          # 캘리브레이션 파이프라인
├── Checker/              # 체커보드 캘리브레이션 이미지
├── Raw_image/            # 원본 파우더 베드 이미지
└── Calibrated_image/     # 보정 결과 + calibration.json
```

## 사용법
```bash
pip install opencv-python numpy
python calibrate.py
```

## 처리 내용
1. 체커보드 5×5 내부 코너 검출 (`findChessboardCornersSB`)
2. 검출 코너 → 실측 20 mm 격자로 매핑하는 호모그래피 계산
3. 동일 호모그래피를 raw 이미지에 적용 → `Calibrated_image/`에 저장

- 스케일: 0.3226 mm/px (3.1 px/mm)
- 재투영 오차: 평균 0.95 px

## 한계
체커보드 이미지가 1장이므로 **평면 원근 + 스케일 보정**만 수행합니다.
렌즈 왜곡 보정은 여러 각도의 체커보드 이미지로 전체 카메라 캘리브레이션이 필요합니다.
