import time

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from engine import analyze_news, stream_collection

load_dotenv()

st.set_page_config(page_title="LangGraph 뉴스 분석 대시보드", page_icon="📰", layout="centered")
st.title("📰 LangGraph 기반 뉴스 분석 앱")
st.write("버튼을 누르면 1초마다 Google News에서 뉴스가 수집되고, 5개가 쌓이면 Claude가 제목을 분석합니다.")

if "collected_data" not in st.session_state:
    st.session_state.collected_data = []

status_box = st.empty()
table_box = st.empty()
count_box = st.empty()

if st.button("데이터 수집 시작", type="primary"):
    st.session_state.collected_data = []
    status_box.info("데이터 수집을 시작합니다...")

    for event in stream_collection():
        time.sleep(1)
        if "messages" in event:
            st.session_state.collected_data.extend(event["messages"])

        df = pd.DataFrame(st.session_state.collected_data)
        count = len(st.session_state.collected_data)

        count_box.metric("수집된 데이터 수", f"{count}/5")
        table_box.dataframe(
            df,
            use_container_width=True,
            column_config={
                "link": st.column_config.LinkColumn("링크"),
            },
        )
        status_box.info(f"수집 진행 중... ({count}/5)")

    status_box.info("뉴스 수집 완료. AI 분석 중...")
    try:
        with st.spinner("Claude가 뉴스 제목을 분석 중입니다..."):
            analyzed = analyze_news(st.session_state.collected_data)
    except ValueError as e:
        status_box.error(str(e))
        df_final = pd.DataFrame(st.session_state.collected_data)
        table_box.dataframe(
            df_final,
            use_container_width=True,
            column_config={"link": st.column_config.LinkColumn("링크")},
        )
    except Exception as e:
        status_box.error(f"AI 분석 중 오류: {e}")
        df_final = pd.DataFrame(st.session_state.collected_data)
        table_box.dataframe(
            df_final,
            use_container_width=True,
            column_config={"link": st.column_config.LinkColumn("링크")},
        )
    else:
        rows = []
        for r in analyzed:
            title = str(r.get("title", ""))
            score = int(r.get("ai_score", 0))
            if score >= 8:
                title = f"🔥 {title}"
            rows.append(
                {
                    "제목": title,
                    "링크": r.get("link", ""),
                    "발행일": r.get("published", ""),
                    "AI 분석 점수": score,
                    "핵심 인사이트": r.get("insight", ""),
                }
            )
        df_final = pd.DataFrame(rows)

        def _highlight_hot(row: pd.Series):
            if row["AI 분석 점수"] >= 8:
                return ["background-color: #fff3cd; font-weight: 600"] * len(row)
            return [""] * len(row)

        styled = df_final.style.apply(_highlight_hot, axis=1)
        table_box.dataframe(
            styled,
            use_container_width=True,
            column_config={
                "링크": st.column_config.LinkColumn("링크"),
                "AI 분석 점수": st.column_config.NumberColumn(
                    "AI 분석 점수", min_value=1, max_value=10, step=1
                ),
            },
        )
        status_box.success("분석 완료")
