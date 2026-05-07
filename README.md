# Site Work Status Map Dashboard

Python/Streamlit 기반의 CSV 운영 현황 지도 대시보드입니다. 팀원이 `sample_site_status.csv`와 같은 형식의 CSV만 업데이트하면 각 site의 위치와 작업 진행 현황을 Folium 지도에서 확인할 수 있습니다.

## 주요 기능

- CSV 업로드 또는 기본 sample CSV 사용
- `enabled` 이후 모든 열을 동적 작업 항목으로 자동 인식
- Folium 기반 zoom in/out 지도
- 작업 항목 선택 체크박스 패널
- 선택 작업 1개일 때: 지도 label에 site name + 해당 작업 세부 상태 직접 표시
- 선택 작업 2개 이상일 때: 지도 label에는 site name만 표시, popup/detail panel에서 상세 확인
- 현재 선택된 작업 기준 marker 색상 자동 계산
- 선택된 작업 중 progress 타입이 있으면 최저 완료율 기준으로 site status 판단
- CSV 오류 검증 및 Data Quality Report 표시
- 필터링된 site status CSV 다운로드
- Data quality issue CSV 다운로드
- sample CSV template 다운로드

## CSV 형식

CSV에는 아래 기본 열이 반드시 필요합니다.

```csv
location_id,location_name,country,state,city,latitude,longitude,timezone,enabled
```

`enabled` 이후에 나오는 모든 열은 작업 항목으로 자동 인식됩니다. 작업명은 코드에 하드코딩하지 않습니다.

예시:

```csv
location_id,location_name,country,state,city,latitude,longitude,timezone,enabled,Valve1, Valve2,Pump ,F/W Version,S/W version
FL001,BLACK RIVER,US,FL,Milton,30.6,-86.9,America/Chicago,Y,60/66,N/A,10/66,3.0.0.0,3.0.0.1
FL002,CAN,US,FL,Holt,30.6,-86.7,America/Chicago,Y,20/183,183/183,183/183,3.0.0.2,3.0.0.6
```

## enabled 값 규칙

지도에 기본 표시되는 값:

- `Y`
- `Yes`
- `TRUE`
- `1`

기본적으로 제외되는 값:

- `N`
- `No`
- `FALSE`
- `0`

sidebar의 `Include disabled sites` 옵션을 켜면 disabled site도 확인할 수 있습니다.

## 작업 항목 입력 규칙

### 1. Progress 값

형식:

```text
완료수/전체수
```

예:

```text
60/66
183/183
10/66
```

앱은 완료율을 자동 계산합니다.

예:

```text
60/66 · 90.9%
```

### 2. N/A 값

아래 값은 Not Applicable로 처리됩니다.

```text
N/A
NA
Not Applicable
n/a
해당없음
```

### 3. Missing 값

빈 값 또는 NaN은 Missing으로 처리되며 Data Quality Report에 WARNING으로 표시됩니다.

### 4. String status 값

progress 형식이 아닌 문자열은 string status로 처리됩니다.

예:

```text
3.0.0.1
Completed
Pending
Delayed
In Progress
```

동일 문자열 값은 항상 같은 색상으로 매핑되도록 설계되어 있습니다.

### 5. Invalid progress 값

아래와 같은 값은 invalid progress로 처리되어 Data Quality Report에 ERROR로 표시됩니다.

```text
10/0
abc/30
10/
```

## 실행 방법

Python 3.11 이상을 권장합니다.

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 샘플 CSV 사용 방법

앱을 실행하면 업로드 파일이 없어도 내장 sample CSV가 자동 로드됩니다. sidebar의 `Download sample CSV template` 버튼으로 template 파일을 다운로드할 수 있습니다.

## 작업 체크박스 사용 방법

작업 항목 선택 패널에서 원하는 작업을 체크하거나 해제합니다.

- `Select All`: 모든 작업 선택
- `Clear All`: 전체 해제 시도. 단, 최소 1개 작업은 유지됩니다.
- `Reset`: 모든 작업 선택 상태로 복구
- `Show site labels`: 지도 label 표시 여부
- `Show all tasks in popup`: popup에 선택되지 않은 작업까지 표시
- `Use marker clustering`: site 수가 많을 때 marker clustering 사용

## 선택 작업 수에 따른 지도 표시 차이

### 선택 작업이 1개일 때

지도 label에 site 이름과 선택된 작업 상태가 직접 표시됩니다.

예:

```text
BLACK RIVER
Valve1: 60/66 · 90.9%
```

### 선택 작업이 2개 이상일 때

지도 label에는 site 이름만 표시됩니다. 작업 상세는 marker 또는 label 클릭 시 popup과 Selected Site Detail Panel에서 확인합니다.

예 popup:

```text
BLACK RIVER
Valve1 : 60/66 · 90.9%
Valve2: N/A
Pump: 10/66 · 15.2%
```

## Marker 색상 기준

선택된 작업 중 progress 타입이 있으면 최저 완료율을 기준으로 marker 색상을 계산합니다. 평균 완료율은 참고용으로 계산하지만 marker 색상 판단에는 사용하지 않습니다.

- 100%: green
- 70% 이상 100% 미만: blue
- 30% 이상 70% 미만: orange
- 30% 미만: red
- N/A only: lightgray
- string status only: gray
- missing/invalid: warning/error indicator

## Data Quality Report

아래 항목을 검증합니다.

- 필수 열 누락
- 중복 `location_id`
- latitude 누락 또는 숫자 변환 실패
- longitude 누락 또는 숫자 변환 실패
- enabled 값 오류
- timezone 값 오류
- progress 형식 오류
- progress 분모 0
- 작업 값 missing
- 작업 열 없음

Severity 기준:

- `ERROR`: 지도 표시 불가 또는 계산 불가
- `WARNING`: 표시 가능하지만 확인 필요
- `INFO`: 참고 사항

## 테스트 시나리오

1. `Valve1`만 선택  
   - `BLACK RIVER`: `60/66 · 90.9%` 표시
   - `CAN`: `20/183 · 10.9%` 표시
   - marker 색상은 `Valve1` 완료율 기준

2. `Water Pump`만 선택  
   - `BLACK RIVER`: `10/66 · 15.2%` 표시
   - `CAN`: `183/183 · 100.0%` 표시
   - marker 색상은 `Water Pump` 완료율 기준

3. `F/W Version`만 선택  
   - version 값이 label에 표시
   - progress가 아니므로 string status/info 기준 색상

4. `Valve1`과 `Valve2` 2개 선택  
   - 지도 label에는 site name만 표시
   - popup/detail panel에 두 작업 상세 표시
   - marker 색상은 progress 작업 중 최저 완료율 기준

5. 모든 작업 선택  
   - 지도 label에는 site name만 표시
   - popup/detail panel에서 전체 작업 확인 가능

6. 모든 작업 체크 해제 시도  
   - 허용하지 않음
   - 마지막 유효 선택 또는 첫 번째 작업을 유지

7. Data Quality Issue 발생  
   - 잘못된 latitude/longitude/progress/중복 location_id가 있어도 앱은 중단되지 않음
   - Data Quality Report에 표시

8. Disabled site 포함 옵션  
   - `enabled=N` site는 기본 숨김

추가 가능 정보:

- owner
- status
- detail
- issue
- action_plan
- due_date
- updated_at
- updated_by
- overdue 여부
- stale update 여부

## 향후 DB 전환

현재는 CSV 기반입니다. 데이터 처리 함수와 UI 렌더링 함수를 분리했으므로 향후 SQLite 또는 PostgreSQL로 전환할 때 CSV loader만 repository/data access layer로 전환 업데이트 예정입니다.


## UI revision notes

This version moves the work-item selector to the top of the left sidebar and moves CSV upload/download controls to the bottom of the sidebar.

Removed from the sidebar:
- Include disabled sites
- Show sites below progress threshold
- String status value

Fixed map options:
- Show site labels: always enabled internally
- Show all tasks in popup: always enabled internally
- Use marker clustering: always enabled internally

Internal columns starting with `_` are excluded from task selection and site detail displays.


## Default CSV

When the app starts without an uploaded file, it loads `site_status.csv` from the project folder and shows it as the current uploaded file. If you upload another CSV from the sidebar, the uploaded file takes priority.

The map automatically fits the initial viewport to all valid enabled sites in the active CSV.
