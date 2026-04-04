import time

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from engine import DEFAULT_KEYWORDS, analyze_news, stream_collection

load_dotenv()

st.set_page_config(page_title="실시간 투자 리서치 생성기", page_icon="📡", layout="centered")

st.markdown(
    """
    <h1 style='margin-bottom: 0;'>📡 실시간 투자 리서치 생성기</h1>
    <p style='font-size: 0.95rem; color: #888; margin-top: 4px;'>
        Analysis by <strong>Jihun</strong>
        &nbsp;·&nbsp;
        <span style='font-size: 0.85rem;'>engineered with <strong>Claude</strong></span>
        &nbsp;
        <span
            title="최신 뉴스(최대 24시간)를 수집하고 Claude가 분석합니다."
            style="cursor: help; color: #aaa; font-size: 0.78rem;
                   border-bottom: 1px dashed #aaa; padding-bottom: 1px;">
            how it works?
        </span>
    </p>
    """,
    unsafe_allow_html=True,
)

# ── 세션 초기화 ──────────────────────────────────────────────────────────────
if "keywords" not in st.session_state:
    st.session_state.keywords = list(DEFAULT_KEYWORDS)
if "collected_data" not in st.session_state:
    st.session_state.collected_data = []
if "analyzed_data" not in st.session_state:   # ← 결과 영구 보존
    st.session_state.analyzed_data = []
if "kw_selected" not in st.session_state:
    st.session_state.kw_selected = list(DEFAULT_KEYWORDS)
if "kw_pills_v" not in st.session_state:
    st.session_state.kw_pills_v = 0

# ── 키워드 배지 ──────────────────────────────────────────────────────────────
st.write("**키워드**")

all_sel = set(st.session_state.kw_selected) >= set(st.session_state.keywords)
c_btn, _ = st.columns([1, 5])
with c_btn:
    if st.button("전체 해제" if all_sel else "전체 선택", key="toggle_all"):
        st.session_state.kw_selected = (
            [] if all_sel else list(st.session_state.keywords)
        )
        st.session_state.kw_pills_v += 1
        st.rerun()

result = st.pills(
    "키워드",
    options=st.session_state.keywords,
    selection_mode="multi",
    default=st.session_state.kw_selected,
    key=f"kw_pills_{st.session_state.kw_pills_v}",
    label_visibility="collapsed",
)
st.session_state.kw_selected = list(result) if result else []

# 새 키워드 추가
with st.form("add_keyword_form", clear_on_submit=True):
    col1, col2 = st.columns([5, 1])
    with col1:
        new_kw = st.text_input(
            "새 키워드",
            label_visibility="collapsed",
            placeholder="새 키워드",
        )
    with col2:
        submitted = st.form_submit_button("추가")
    if submitted and new_kw.strip():
        kw_stripped = new_kw.strip()
        if kw_stripped not in st.session_state.keywords:
            st.session_state.keywords.append(kw_stripped)
            st.session_state.kw_selected.append(kw_stripped)
            st.session_state.kw_pills_v += 1
        st.rerun()

st.divider()

# ── 키워드당 수집 수량 ────────────────────────────────────────────────────────
per_keyword_count = st.select_slider(
    "키워드당 수집 기사 수",
    options=[1, 2, 3, 4, 5],
    value=3,
)

st.divider()

# ── 결과 테이블 HTML 빌더 ─────────────────────────────────────────────────────
def _build_results_html(analyzed: list) -> str:
    css = """
    <style>
    body { margin: 0; font-family: sans-serif; }
    .rt { width:100%; border-collapse:collapse; font-size:0.875rem; }
    .rt th { background:#f0f2f6; padding:8px 12px; text-align:left;
              border-bottom:2px solid #ddd; white-space:nowrap; }
    .rt td { padding:8px 12px; border-bottom:1px solid #eee; vertical-align:top; }
    .rt tr.yellow td { background-color:#fffde7; }
    .rt tr.red    td { background-color:#ffebee; }
    .rt .num { color:#aaa; font-size:0.8rem; text-align:center; }
    .rt .eff { font-weight:700; text-align:center; }
    .rt .pub { white-space:nowrap; font-size:0.78rem; color:#888; }
    .rt a.tl { color:inherit; text-decoration:none; }
    .rt a.tl:hover { text-decoration:underline; color:#1976d2; }
    .rt a.fn { font-size:0.7rem; vertical-align:super; color:#1976d2;
               text-decoration:none; margin-left:3px; }
    .rt a.fn:hover { text-decoration:underline; }
    </style>
    """
    thead = """
    <table class="rt">
    <thead><tr>
      <th>#</th>
      <th>키워드</th>
      <th>Effect</th>
      <th>제목</th>
      <th>발행일</th>
      <th>핵심 인사이트</th>
    </tr></thead><tbody>
    """
    tbody = ""
    for i, r in enumerate(analyzed, 1):
        score   = int(r.get("ai_score", 0))
        title   = str(r.get("title", ""))
        link    = str(r.get("link", ""))
        pub     = str(r.get("published", ""))
        kw      = str(r.get("keyword", ""))
        insight = str(r.get("insight", ""))

        row_cls = "red" if score >= 9 else ("yellow" if score >= 7 else "")

        # 제목 셀: link 값을 href에 직접 연결
        title_cell = (
            f'<a href="{link}" target="_blank" class="tl">{title}</a>'
            if link else title
        )
        footnote = (
            f'<a href="{link}" target="_blank" title="{link}" class="fn">[{i}]</a>'
            if link else ""
        )
        insight_cell = f"{insight}{footnote}"

        tbody += (
            f'<tr class="{row_cls}">'
            f'<td class="num">{i}</td>'
            f"<td>{kw}</td>"
            f'<td class="eff">{score}</td>'
            f"<td>{title_cell}</td>"
            f'<td class="pub">{pub}</td>'
            f"<td>{insight_cell}</td>"
            f"</tr>\n"
        )

    return css + thead + tbody + "</tbody></table>"


# ── 상태·스트리밍 표시 영역 (수집 중에만 사용) ──────────────────────────────
status_box  = st.empty()
stream_table = st.empty()
count_box   = st.empty()

# ── 기사 수집 버튼 ────────────────────────────────────────────────────────────
if st.button("기사 수집", type="primary"):
    active_keywords = st.session_state.kw_selected

    if not active_keywords:
        status_box.warning("수집할 키워드를 하나 이상 선택하세요.")
    else:
        # 새 수집 시작 → 이전 결과 초기화
        st.session_state.analyzed_data = []
        st.session_state.collected_data = []
        max_total = per_keyword_count * len(active_keywords)

        status_box.info("데이터 수집을 시작합니다...")
        total_articles = max_total

        for event in stream_collection(active_keywords, per_keyword_count, max_total):
            if "meta" in event:
                total_articles = event["meta"]["total"]
                if total_articles == 0:
                    status_box.warning("수집된 기사가 없습니다. 키워드를 확인하세요.")
                continue

            time.sleep(1)
            if "messages" in event:
                st.session_state.collected_data.extend(event["messages"])

            count = len(st.session_state.collected_data)
            raw_df = pd.DataFrame(st.session_state.collected_data)
            stream_cols = [
                c for c in ["id", "keyword", "title", "published"]
                if c in raw_df.columns
            ]
            count_box.metric("수집된 데이터 수", f"{count}/{total_articles}")
            stream_table.dataframe(raw_df[stream_cols], use_container_width=True, hide_index=True)
            status_box.info(f"수집 진행 중... ({count}/{total_articles})")

        if not st.session_state.collected_data:
            status_box.warning("수집된 기사가 없습니다.")
        else:
            status_box.info("뉴스 수집 완료. AI 분석 중...")
            try:
                with st.spinner("Claude가 뉴스 제목을 분석 중입니다..."):
                    analyzed = analyze_news(st.session_state.collected_data)
                st.session_state.analyzed_data = analyzed   # ← 세션에 보존
                stream_table.empty()
                count_box.empty()
                status_box.success("분석 완료")
            except ValueError as e:
                status_box.error(str(e))
            except Exception as e:
                status_box.error(f"AI 분석 중 오류: {e}")

# ── 결과 테이블: 세션에 데이터가 있으면 항상 표시 (rerun에도 유지) ──────────
if st.session_state.analyzed_data:
    st.html(_build_results_html(st.session_state.analyzed_data))
