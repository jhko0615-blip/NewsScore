import time

import pandas as pd
import streamlit as st

from engine import stream_collection


st.set_page_config(page_title="LangGraph 뉴스 분석 대시보드", page_icon="📰", layout="centered")
st.title("📰 LangGraph 기반 뉴스 분석 앱")
st.write("버튼을 누르면 1초마다 Google News에서 뉴스가 수집되고, 5개가 쌓이면 분석이 완료됩니다.")

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

    status_box.success("분석 완료")
