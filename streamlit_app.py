import subprocess
import time

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from engine import DEFAULT_KEYWORDS, analyze_news, stream_collection

load_dotenv(override=True)

# ── 버전 태그 ─────────────────────────────────────────────────────────────────
try:
    _version = subprocess.check_output(
        ["git", "describe", "--tags", "--abbrev=0"],
        stderr=subprocess.DEVNULL,
    ).decode().strip()
except Exception:
    _version = ""

st.set_page_config(page_title="실시간 투자 리서치 생성기", page_icon="📡", layout="centered")

st.markdown(
    f"""
    <h1 style='margin-bottom: 0;'>
        📡 실시간 투자 리서치 생성기
        <span style='font-size:0.75rem; color:#bbb; font-weight:400;
                     vertical-align:middle; margin-left:8px;'>{_version}</span>
    </h1>
    <p style='font-size: 0.95rem; color: #888; margin-top: 4px; margin-bottom: 24px;'>
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
if "analyzed_data" not in st.session_state:
    st.session_state.analyzed_data = []
if "kw_selected" not in st.session_state:
    st.session_state.kw_selected = list(DEFAULT_KEYWORDS)
if "kw_pills_v" not in st.session_state:
    st.session_state.kw_pills_v = 0
if "kw_input_v" not in st.session_state:
    st.session_state.kw_input_v = 0

# ── 키워드 배지 ──────────────────────────────────────────────────────────────
all_sel = set(st.session_state.kw_selected) >= set(st.session_state.keywords)

col_label, col_pills = st.columns([1, 8])
with col_label:
    st.markdown("<div style='padding-top:8px; font-weight:bold;'>키워드</div>", unsafe_allow_html=True)
with col_pills:
    result = st.pills(
        "키워드",
        options=st.session_state.keywords,
        selection_mode="multi",
        default=st.session_state.kw_selected,
        key=f"kw_pills_{st.session_state.kw_pills_v}",
        label_visibility="collapsed",
    )
st.session_state.kw_selected = list(result) if result else []

# 새 키워드 추가 + 전체 선택/해제
col_input, col_add, col_toggle = st.columns([5, 1, 1])
with col_input:
    new_kw = st.text_input(
        "새 키워드",
        label_visibility="collapsed",
        placeholder="새 키워드",
        key=f"kw_input_{st.session_state.kw_input_v}",
    )
with col_add:
    if st.button("추가", key="btn_add"):
        if new_kw.strip():
            kw_stripped = new_kw.strip()
            if kw_stripped not in st.session_state.keywords:
                st.session_state.keywords.append(kw_stripped)
                st.session_state.kw_selected.append(kw_stripped)
                st.session_state.kw_pills_v += 1
            st.session_state.kw_input_v += 1
            st.rerun()
with col_toggle:
    if st.button("전체 해제" if all_sel else "전체 선택", key="toggle_all"):
        st.session_state.kw_selected = (
            [] if all_sel else list(st.session_state.keywords)
        )
        st.session_state.kw_pills_v += 1
        st.rerun()

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


# ── 상태·스트리밍 표시 영역 ───────────────────────────────────────────────────
status_box   = st.empty()
stream_table = st.empty()
count_box    = st.empty()

# ── 기사 수집 (슬라이더 + 버튼 같은 행) ──────────────────────────────────────
col_slider, col_btn = st.columns([3, 1])
with col_slider:
    per_keyword_count = st.select_slider(
        "키워드당 수집 기사 수",
        options=[1, 2, 3, 4, 5],
        value=3,
    )
with col_btn:
    st.markdown("<div style='padding-top:22px;'></div>", unsafe_allow_html=True)
    collect_clicked = st.button("기사 수집", type="primary")

if collect_clicked:
    active_keywords = st.session_state.kw_selected

    if not active_keywords:
        status_box.warning("수집할 키워드를 하나 이상 선택하세요.")
    else:
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
                with st.spinner("Claude 분석 중"):
                    analyzed = analyze_news(st.session_state.collected_data)
                st.session_state.analyzed_data = analyzed
                stream_table.empty()
                count_box.empty()
                status_box.success("분석 완료")
            except ValueError as e:
                status_box.error(str(e))
            except Exception as e:
                status_box.error(f"AI 분석 중 오류: {e}")

# ── 결과 테이블 ───────────────────────────────────────────────────────────────
if st.session_state.analyzed_data:
    st.html(_build_results_html(st.session_state.analyzed_data))
