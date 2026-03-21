from __future__ import annotations

import urllib.parse
import operator
from typing import Annotated, Any, Dict, List, TypedDict

import feedparser
from langgraph.graph import END, StateGraph


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
