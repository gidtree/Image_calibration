# HANDOFF — Edge PC 자동화 작업 인수인계

이 문서는 **Edge PC(Linux)의 Claude Code가 이어받아** 자동 보정 서비스를 구축하기 위한 명세입니다.
개발 PC(Windows)에서 캘리브레이션과 런타임 적용 모듈까지 완료했고, 남은 것은 이를 **상시 서비스로
감싸는 것**입니다.

---

## 1. 이 프로젝트가 하는 일
고정된 파우더 베드 모니터링 카메라의 raw 이미지를, 체커보드로 구한 보정값을 이용해
**렌즈 왜곡(k1) + 원근 왜곡**을 펴고 실측 스케일(mm/px)이 부여된 top-down 이미지로 변환합니다.

## 2. 이미 완료된 것 (이 저장소에 포함)
| 파일 | 역할 |
|---|---|
| `calibrate.py` | **오프라인 1회용.** 체커보드 이미지 → `calibration.json` 생성 |
| `Calibrated_image/calibration.json` | **재사용 보정값** (K, 왜곡계수 k1, 호모그래피, output_size). 전부 숫자, 경로 없음 → 이식 가능 |
| `apply_calibration.py` | **런타임 모듈.** `calibration.json` 로드 → 이미지에 적용. 크로스플랫폼, 하드코딩 경로 없음 |
| `README.md` | 캘리브레이션 방법론·모델 선택 근거 |

> **핵심**: 카메라 구도가 **항상 고정**이라, 캘리브레이션은 다시 하지 않습니다.
> 지금 있는 `calibration.json`을 모든 이미지에 **그대로** 적용하면 됩니다.
> (렌즈/카메라 위치가 바뀌면 그때만 새 체커보드로 `calibrate.py` 재실행)

## 3. 확정된 설계 결정
- **Edge PC OS**: Linux
- **수집 방식**: Edge PC가 **촬영 PC의 공유 폴더를 pull** (촬영 PC → Edge)
- **출력**: 보정본을 **NAS**에 저장 (Edge → NAS)
- **캘리브레이션**: 정적(고정 구도) — 런타임 루프에서 재캘리 없음

```
[촬영 PC 공유폴더] --pull--> [Edge PC: 감시+적용 서비스] --write--> [NAS]
                                     │
                          calibration.json (재사용)
```

## 4. Edge Claude가 할 일 — 자동 적용 서비스 구축
`apply_calibration.Calibrator` 를 감싸서, 아래를 만족하는 상시 서비스를 구현하세요.

**동작**
1. 촬영 PC 공유 폴더(SMB 마운트 또는 rsync 소스)에서 **새 raw 이미지를 감지/가져오기**
2. `Calibrator.apply_file()` 로 보정
3. 결과를 **NAS 출력 폴더**에 저장
4. 처리한 원본은 아카이브 또는 처리완료 표시

**요구사항 (robustness)**
- **폴링 방식 권장** — SMB/네트워크 마운트는 inotify 이벤트가 불안정. 수 초 간격 폴링이 안정적
- **부분 파일 방지** — 복사 중 파일을 잡지 않도록 (파일 크기가 N초간 불변인지 확인, 또는 `.tmp`→rename)
- **멱등성(idempotent)** — 이미 처리한 파일 재처리 방지 (처리 목록/상태 파일 또는 done/ 이동)
- **에러 격리** — 실패 이미지는 `failed/`로 이동 + 로그, 서비스는 계속
- **로깅** — 처리 건수/시각/에러를 로그 파일로
- **재시작 견딤** — 서비스 재시작/재부팅 후에도 밀린 파일 이어서 처리
- **systemd 서비스**로 등록 (부팅 시 자동 시작, 실패 시 재시작)

**제안 폴더 구조 (Edge PC)**
```
/opt/image_calib/
├── apply_calibration.py
├── calibration.json
├── watch_service.py        # <- 새로 만들 파일
├── logs/
/mnt/source_pc/incoming/    # 촬영 PC 공유폴더 (마운트)
/mnt/nas/calibrated/        # NAS 출력 (마운트)
```

## 5. 시작하기
```bash
git clone https://github.com/gidtree/Image_calibration.git
cd Image_calibration
pip install opencv-python numpy      # 또는 opencv-python-headless (Edge/서버 권장)

# 동작 확인 (샘플 raw로 테스트 — Calibrated_image/ 결과와 동일해야 함)
python apply_calibration.py \
    --calib Calibrated_image/calibration.json \
    --input Raw_image \
    --output /tmp/out
```
> 서버/헤드리스 환경은 `opencv-python-headless` 를 쓰세요 (GUI 의존성 없음).

## 6. 주의사항
- `calibration.json` 의 `work_area_polygon_calibrated_px` = 정확도가 검증된 **작업영역**. 그 밖은 왜곡 외삽이라 신뢰 X (관심 대상 아님)
- 보정본에서 큐브가 입체적으로 보이는 건 **큐브 높이 시차** — 캘리브레이션 오차 아님 (평면 보정의 정상 현상)
- 스케일: `mm_per_px ≈ 0.3226` — 필요 시 측정에 사용
- 출력은 무손실 PNG. 용량이 문제면 포맷/압축은 Edge에서 조정
