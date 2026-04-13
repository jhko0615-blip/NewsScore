# CLAUDE.md — 실시간 투자 리서치 생성기

## 프로젝트 개요

Google News RSS로 투자 관련 최신 뉴스를 수집하고, Claude API로 시장 영향력을 분석해 보여주는 Streamlit 대시보드.

- **레포**: https://github.com/jhko0615-blip/NewsScore
- **작업 브랜치**: `claude/sharp-edison`
- **실행**: `python -m streamlit run streamlit_app.py`
- **주요 파일**: `engine.py` (수집·분석 엔진), `streamlit_app.py` (UI)

---

## 핵심 아키텍처

```
키워드 선택 (st.pills)
    ↓
fetch_google_news() — Google News RSS 수집
    ├─ 1단계: 우선 출처 combined OR 쿼리
    │         (bloomberg.com, finance.yahoo.com, investing.com, cnbc.com)
    └─ 2단계: 부족하면 일반 검색으로 보충
    ↓
LangGraph — 수집된 기사를 한 건씩 스트리밍으로 UI에 표시
    ↓
analyze_news() — Claude API로 시장 영향력 분석 (score 1-10, 한줄 인사이트)
    ↓
st.html() — 커스텀 HTML 결과 테이블 렌더링
```

---

## 주요 설계 결정 및 배경

### 뉴스 수집
- **우선 출처 쿼리 방식**: `bloomberg` 등 사이트별 개별 쿼리는 Google News RSS에서 신뢰도가 낮았음. `keyword (site:bloomberg.com OR site:finance.yahoo.com OR ...)` combined OR 쿼리가 정상 동작함.
- **24시간 필터**: `published_parsed` 또는 `updated_parsed` 파싱 → UTC 기준 24시간 초과 기사 등장 시 해당 키워드 피드 즉시 종료 (최신순 정렬 가정). 파싱 불가 기사는 스킵(포함 아님).
- **우선 출처는 24시간 필터 적용**: 출처별 게재 주기가 달라도 combined 쿼리 결과는 최신순이므로 동일 규칙 적용.
- **최신순 정렬 후 slice**: 전체 키워드 수집 후 `published_dt` 내림차순 → `max_total` 개 반환.

### LangGraph 역할
- 할루시네이션 방지나 교차검증 로직 **없음**.
- 단순히 수집된 기사 리스트를 한 건씩 `messages`로 emit하는 스트리밍 파이프라인 역할만 함.
- `CollectorState`: messages, count, articles, current_index

### Claude 분석 (analyze_news)
- 입력: 수집된 기사 제목 목록 (numbered)
- 출력: JSON 배열 `[{index, score, summary}]`
- 모델: `claude-3-5-sonnet-20241022`
- score 범위 클램핑: `max(1, min(10, score))`
- JSON 파싱: 마크다운 코드펜스 제거 후 `\[...\]` 추출

### UI (streamlit_app.py)
- **키워드**: `st.pills` (selection_mode="multi") + 전체 선택/해제. 버전 키(`kw_pills_v`) 트릭으로 select-all 강제 리렌더링.
- **결과 테이블**: `st.html()` 사용. `st.markdown(unsafe_allow_html=True)`는 `<a>` 태그 sanitize 이슈 있어서 교체함.
- **결과 유지**: `st.session_state.analyzed_data`에 보존 → 키워드 변경 등 rerun에도 휘발 안 됨. 버튼 블록 **밖**에서 항상 렌더링.
- **테이블 컬럼 순서**: `# | 키워드 | Effect | 제목(하이퍼링크) | 발행일 | 핵심 인사이트(각주[n])`
- **하이라이트**: Effect 7-8점 → 노란색(`#fffde7`), 9-10점 → 빨간색(`#ffebee`)

---

## 환경 설정

```
# .env (깃 미포함)
ANTHROPIC_API_KEY=sk-ant-...
```

```
# requirements.txt
streamlit, langgraph, langchain, pandas, feedparser, anthropic, python-dotenv
```

---

## 알려진 이슈 / 미구현

- **할루시네이션 방지 없음**: Claude가 제목만 보고 summary 생성 → 과잉 해석 가능. 본문 포함 또는 후처리 검증 미적용.
- **Google News 링크**: `news.google.com/rss/articles/...` 형태의 redirect URL. 원문 URL 직접 추출 미구현.
- **`st.pills` select-all 버그 가능성**: 버전 키 트릭 사용 중. 키워드 추가 시 `kw_pills_v` 증가 + `kw_selected`에 자동 추가.
