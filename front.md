aqsys-frontend
서울시 대기질 기반 야외운동 시간대 추천 서비스 - 프론트엔드 (HTML/CSS/JavaScript)

프론트엔드 명세서
서울시 대기질 기반 야외운동 시간대 추천 서비스
1. 기술 스택
   항목	선택	비고
   마크업	HTML5	-
   스타일	CSS3	별도 .css 파일 분리
   로직	Vanilla JavaScript (ES6+)	프레임워크 미사용
   차트	Chart.js (CDN)	PM 농도 그래프
   HTTP 요청	fetch API	백엔드 REST API 호출
   Chart.js CDN 추가 이유: 시간대별 PM 농도 그래프를 순수 JS로 직접 그리는 건 공수가 크기 때문. 라이브러리 설치 없이 CDN 한 줄로 바로 사용 가능.

2. 파일 구조
   frontend/
   ├── index.html         메인 페이지 (입력 폼)
   ├── result.html        결과 페이지 (신호등 타임라인, 그래프 등)
   ├── css/
   │   └── style.css
   ├── js/
   │   ├── main.js        입력 폼 로직, 백엔드 API 호출
   │   ├── result.js      결과 렌더링 (신호등, 그래프, 추천)
   │   └── mock.js        목 데이터 (백엔드 API 완성 전 개발용)
   └── assets/
   └── icons/         신호등 아이콘 등
3. 화면 구성
   3.1 입력 폼 (index.html)
   입력 요소	타입	항목
   자치구 선택	<select> 드롭다운	서울시 25개 자치구
   운동 종류 선택	<select> 드롭다운	걷기 / 조깅 / 자전거 / 등산 / 구기운동
   희망 날짜 선택	<input type="date">	오늘 ~ 최대 1일 후
   조회 버튼	<button>	클릭 시 API 요청 → result.html로 이동
   3.2 결과 화면 (result.html)
   섹션	내용
   신호등 타임라인	24시간 각 시간대를 녹색/노랑/빨강 막대로 표시
   PM 농도 그래프	Chart.js 라인 차트, PM10·PM2.5 시간별 예측값
   추천 시간대 요약	한 줄 텍스트 (예: "오전 7~8시 운동을 추천합니다")
   권장 지속시간	운동 종류별 권장 운동 시간 (분 단위)
   다시 검색 버튼	index.html로 복귀
4. 백엔드 API 연동 스펙
   4.1 기본 정보
   항목	내용
   베이스 URL	http://localhost:8000 (개발) / 추후 배포 URL로 교체
   데이터 형식	JSON
   인증	없음 (팀 내부 프로젝트)
   CORS	백엔드에서 허용 설정 필요 (프론트가 다른 포트에서 fetch 호출하므로)
   4.2 추천 조회 API
   Request
   GET /api/recommend?district=강남구&exercise=jogging&date=2026-05-18
   쿼리 파라미터

파라미터	타입	필수	허용값	예시
district	string	✅	서울시 25개 자치구 한글명	강남구
exercise	string	✅	walking / jogging / cycling / hiking / ball	jogging
date	string	✅	YYYY-MM-DD, 오늘 또는 내일만 허용	2026-05-18
Response 예시
{
"district": "강남구",
"exercise": "jogging",
"date": "2026-05-18",
"generated_at": "2026-05-18T08:30:00+09:00",
"timeline": [
{
"hour": 0,
"level": "green",
"pm10": 28.0,
"pm25": 15.0,
"o3": 0.02
},
{
"hour": 1,
"level": "green",
"pm10": 26.5,
"pm25": 14.2,
"o3": 0.02
}
],
"recommended_hours": [7, 8, 20],
"best_hour": 7,
"summary": "오전 7~8시 운동을 추천합니다. 이 시간대 PM2.5 농도가 가장 낮습니다.",
"recommended_duration_min": 40
}
Response 필드 설명

필드	타입	설명
district	string	요청한 자치구
exercise	string	요청한 운동 종류
date	string	요청한 날짜
generated_at	string	예측 생성 시각 (ISO 8601, KST)
timeline	array	0시~23시, 반드시 24개 항목
timeline[].hour	integer	시간 (0~23)
timeline[].level	string	green / yellow / red
timeline[].pm10	float	PM10 예측 농도 (㎍/㎥)
timeline[].pm25	float	PM2.5 예측 농도 (㎍/㎥)
timeline[].o3	float	오존 예측 농도 (ppm)
recommended_hours	array	추천 시간대 목록 (최대 3개)
best_hour	integer	가장 적합한 시간 1개
summary	string	한 줄 추천 요약 텍스트
recommended_duration_min	integer	권장 운동 지속시간 (분)
신호등 등급 기준 (백엔드에서 계산 후 level 값으로 전달, 프론트는 색만 표시)

level 값	표시 색상	의미
green	🟢 녹색	운동 적합
yellow	🟡 노랑	주의 권장
red	🔴 빨강	운동 비권장
level 계산은 백엔드에서. 프론트는 level 문자열만 받아 색을 입히면 됨. 농도 기준을 프론트에 하드코딩하지 않는다.

4.3 에러 응답 예시
모든 에러는 아래 형식으로 통일한다.

{
"error": {
"code": "INVALID_DISTRICT",
"message": "유효하지 않은 자치구입니다."
}
}
에러 코드 목록

HTTP 상태	code	발생 상황	프론트 처리
400	INVALID_DISTRICT	허용되지 않은 자치구 값	"올바른 자치구를 선택해주세요" 알림
400	INVALID_EXERCISE	허용되지 않은 운동 값	"올바른 운동 종류를 선택해주세요" 알림
400	INVALID_DATE	오늘/내일 외의 날짜	"오늘 또는 내일 날짜만 선택 가능합니다" 알림
503	MODEL_UNAVAILABLE	AI 모델 추론 실패	"잠시 후 다시 시도해주세요" 알림
500	INTERNAL_ERROR	서버 내부 오류	"서버 오류가 발생했습니다" 알림
5. 목 데이터 전략
   백엔드 API 완성 전까지 mock.js에 하드코딩된 응답 데이터를 사용해 프론트 개발을 독립적으로 진행한다.

// mock.js
const MOCK_RESPONSE = {
district: "강남구",
exercise: "jogging",
date: "2026-05-18",
timeline: [
{ hour: 7,  level: "green",  pm10: 28.0, pm25: 15.0, o3: 0.02 },
{ hour: 8,  level: "green",  pm10: 31.0, pm25: 17.0, o3: 0.02 },
{ hour: 9,  level: "yellow", pm10: 52.0, pm25: 29.0, o3: 0.04 },
{ hour: 10, level: "yellow", pm10: 55.0, pm25: 31.0, o3: 0.05 },
{ hour: 11, level: "red",    pm10: 82.0, pm25: 48.0, o3: 0.07 }
// ... 24시간치
],
recommended_hours: [7, 8, 20],
summary: "오전 7~8시 운동을 추천합니다",
recommended_duration_min: 40
};
백엔드 API 완성 시 main.js의 데이터 소스를 mock → fetch로 교체하는 것만으로 전환 완료 (?)

6. 📝 미결정 및 추가 검토 사항
   항목	현재 상태	결정 필요 이유 및 조치 사항
   조회 중 상태 표시 (로딩)	추가 예정	API 호출 및 AI 모델 추론에 시간이 소요되므로, 사용자 경험(UX) 향상을 위해 로딩 바 또는 대기 안내 페이지 구현 필요.
   오존(
   O
   3
   ) 신호등 반영 여부	미정	서비스 주제에는 포함되어 있으나, 현재 AI 모델의 예측 대상에는 미포함되어 있어 데이터 조율 필요.
   운동별 호흡량 보정 계수 출처	미정	백엔드 비즈니스 로직 산출을 위한 정확한 기준값(논문 및 공공 데이터 등) 출처 확보 필요.
   result.html 데이터 전달 방식	미정	입력 폼 값을 URL 파라미터(Query String)로 넘길지, localStorage를 사용할지 프론트엔드 통신 방식 결정 필요.
   반응형(모바일) 디자인 지원 여부	미정	CSS layout(Flex/Grid) 설계 방향 및 모바일 웹 뷰 최적화 여부 결정 필요.