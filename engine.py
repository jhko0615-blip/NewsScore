from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import operator
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Dict, List, Optional, TypedDict

import feedparser
from anthropic import Anthropic
from dotenv import load_dotenv
from langgraph.graph import END, StateGraph

load_dotenv(override=True)

CLAUDE_MODEL = "claude-sonnet-4-6"

DEFAULT_KEYWORDS = ["iran", "DXY", "gold", "silver", "WTI", "oil", "bitcoin", "macro"]

# 우선 출처 — combined OR 쿼리로 Google News RSS에 전달
NEWS_SITE_FILTER = (
    "(site:bloomberg.com OR site:finance.yahoo.com"
    " OR site:investing.com OR site:cnbc.com)"
)

MAX_AGE_HOURS = 24


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
                "keyword": article.get("keyword", ""),
                "title": article["title"],
                "link": article["link"],
                "published": article["published"],
            }
        ],
        "count": next_count,
        "current_index": state["current_index"] + 1,
    }


def should_continue(state: CollectorState) -> str:
    if state["current_index"] < len(state["articles"]):
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


def _entry_datetime(entry: Any) -> Optional[datetime]:
    """feedparser 엔트리에서 UTC datetime을 추출. 파싱 불가 시 None."""
    pp = entry.get("published_parsed") or entry.get("updated_parsed")
    if not pp:
        return None
    try:
        return datetime(*pp[:6], tzinfo=timezone.utc)
    except Exception:
        return None


def fetch_google_news(
    keywords: List[str],
    per_keyword: int = 3,
    max_total: int = 30,
) -> List[Dict[str, Any]]:
    """
    키워드별로 Google News RSS를 조회한다.
    - 우선 출처(Bloomberg, Yahoo Finance, Investing.com, CNBC) combined OR 쿼리로 단일 요청.
    - 발행일 파싱 불가 기사는 스킵.
    - 최신순 가정: 24시간 초과 기사 등장 시 해당 키워드 스트림 종료.
    - 부족하면 일반 검색(우선 출처 없이)으로 보충 — 동일한 24시간 규칙 적용.
    - 전체 수집 후 최신순 정렬 → max_total 개 반환.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
    articles: List[Dict[str, Any]] = []
    seen_links: set = set()
    keyword_counts: Dict[str, int] = {kw: 0 for kw in keywords}

    def _scrape(query: str, kw: str) -> None:
        """RSS 한 피드를 순서대로 읽어 keyword_counts[kw] < per_keyword 까지 수집."""
        url = (
            "https://news.google.com/rss/search?"
            f"q={urllib.parse.quote(query)}&hl=en&gl=US&ceid=US:en"
        )
        feed = feedparser.parse(url)
        for entry in feed.entries:
            if keyword_counts[kw] >= per_keyword:
                break
            link = (entry.get("link") or "").strip()
            if not link or link in seen_links:
                continue
            dt = _entry_datetime(entry)
            if dt is None:
                continue                     # 날짜 파싱 불가 → 스킵
            if dt < cutoff:
                break                        # 최신순 가정: 이후 기사도 오래됨 → 종료
            seen_links.add(link)
            keyword_counts[kw] += 1
            articles.append(
                {
                    "keyword": kw,
                    "title": entry.get("title", "제목 없음"),
                    "link": link,
                    "published": entry.get("published", ""),
                    "published_dt": dt,
                }
            )

    for kw in keywords:
        # 1단계: 우선 출처 combined 쿼리
        _scrape(f"{kw} {NEWS_SITE_FILTER}", kw)

        # 2단계: 부족하면 일반 검색으로 보충
        if keyword_counts[kw] < per_keyword:
            _scrape(kw, kw)

        time.sleep(0.25)

    # 최신순 정렬 → max_total 개 슬라이스 → published_dt 제거
    articles.sort(key=lambda x: x["published_dt"], reverse=True)
    articles = articles[:max_total]
    for a in articles:
        a.pop("published_dt", None)

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
    load_dotenv(override=True)
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


def stream_collection(keywords: List[str], per_keyword_count: int = 3, max_total: int = 30):
    articles = fetch_google_news(keywords, per_keyword_count, max_total)
    total = len(articles)
    yield {"meta": {"total": total}}

    if total == 0:
        yield {"node": "empty", "messages": [], "collected_empty": True}
        return

    initial_state: CollectorState = {
        "messages": [],
        "count": 0,
        "articles": articles,
        "current_index": 0,
    }
    for event in app.stream(initial_state, stream_mode="updates"):
        node_name, update = next(iter(event.items()))
        yield {"node": node_name, **update}
