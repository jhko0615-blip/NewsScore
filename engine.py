from __future__ import annotations

import json
import os
import re
import urllib.parse
import operator
from typing import Annotated, Any, Dict, List, TypedDict

import feedparser
from anthropic import Anthropic
from dotenv import load_dotenv
from langgraph.graph import END, StateGraph

load_dotenv()

CLAUDE_MODEL = "claude-3-5-sonnet-20241022"


class CollectorState(TypedDict):
    messages: Annotated[List[Dict[str, Any]], operator.add]
    count: int
    articles: List[Dict[str, Any]]
    current_index: int


def collect_data(state: CollectorState) -> Dict[str, Any]:
    article = state["articles"][state["current_index"]]
    next_count = state["count"] + 1
    return {
        "messages": [
            {
                "id": next_count,
                "title": article["title"],
                "link": article["link"],
                "published": article["published"],
            }
        ],
        "count": next_count,
        "current_index": state["current_index"] + 1,
    }


def should_continue(state: CollectorState) -> str:
    if state["count"] < 5 and state["current_index"] < len(state["articles"]):
        return "collect"
    return "end"


def build_graph():
    graph = StateGraph(CollectorState)
    graph.add_node("collect", collect_data)
    graph.set_entry_point("collect")
    graph.add_conditional_edges(
        "collect",
        should_continue,
        {
            "collect": "collect",
            "end": END,
        },
    )
    return graph.compile()


app = build_graph()


def fetch_google_news(max_items: int = 5) -> List[Dict[str, Any]]:
    query = urllib.parse.quote("비트코인 OR 거시경제")
    url = f"https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
    feed = feedparser.parse(url)

    articles: List[Dict[str, Any]] = []
    for entry in feed.entries[:max_items]:
        articles.append(
            {
                "title": entry.get("title", "제목 없음"),
                "link": entry.get("link", ""),
                "published": entry.get("published", "발행일 정보 없음"),
            }
        )
    return articles


def _parse_json_array_from_llm(text: str) -> List[Dict[str, Any]]:
    """Extract JSON array from model output (handles markdown fences)."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fence:
        text = fence.group(1).strip()
    match = re.search(r"\[[\s\S]*\]", text)
    if match:
        text = match.group(0)
    return json.loads(text)


def analyze_news(news_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    수집된 뉴스 제목들을 Anthropic Claude로 분석합니다.

    각 항목에 ``ai_score`` (1-10, 시장 영향력)와 ``insight`` (전략적 요약 한 줄)를 추가해 반환합니다.
    """
    load_dotenv()
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key or api_key == "your_key_here":
        raise ValueError(
            ".env에 ANTHROPIC_API_KEY를 실제 키로 설정해 주세요. (현재는 플레이스홀더입니다.)"
        )

    if not news_items:
        return []

    titles = [str(item.get("title", "")).strip() for item in news_items]
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(titles))

    user_prompt = f"""다음은 뉴스 제목 {len(titles)}개입니다. 비트코인·거시경제 관점에서 각 제목의 **[시장 영향력]**과 **[전략적 의미]**를 평가하세요.

제목 목록:
{numbered}

반드시 아래 형식의 JSON 배열만 출력하세요. 다른 설명·서문·후문은 넣지 마세요.
[
  {{"index": 1, "score": 7, "summary": "한 줄 전략적 요약 (한국어)"}},
  ...
]

규칙:
- index: 위 목록의 번호(1부터 {len(titles)}까지)와 동일해야 합니다.
- score: 1(시장 영향 거의 없음)~10(시장 영향 매우 큼) 정수. **[시장 영향력 점수 (1-10)]**에 해당합니다.
- summary: **[전략적 요약 (한 줄)]** — 투자·리스크·거시 관점에서 한 문장으로 요약합니다."""

    client = Anthropic(api_key=api_key)
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw = message.content[0].text
    parsed = _parse_json_array_from_llm(raw)

    # index -> {score, summary}
    by_index: Dict[int, Dict[str, Any]] = {}
    for row in parsed:
        idx = int(row.get("index", 0))
        score = row.get("score")
        summary = row.get("summary", "")
        try:
            score_int = int(score)
        except (TypeError, ValueError):
            score_int = 5
        score_int = max(1, min(10, score_int))
        by_index[idx] = {"score": score_int, "summary": str(summary).strip() or "(요약 없음)"}

    result: List[Dict[str, Any]] = []
    for i, item in enumerate(news_items):
        idx = i + 1
        extra = by_index.get(idx, {"score": 5, "summary": "(모델 응답에 해당 항목이 없습니다.)"})
        merged = {**item, "ai_score": extra["score"], "insight": extra["summary"]}
        result.append(merged)

    return result


def stream_collection():
    articles = fetch_google_news(max_items=5)
    initial_state: CollectorState = {
        "messages": [],
        "count": 0,
        "articles": articles,
        "current_index": 0,
    }
    for event in app.stream(initial_state, stream_mode="updates"):
        node_name, update = next(iter(event.items()))
        yield {"node": node_name, **update}
