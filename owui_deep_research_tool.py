"""
title: Deep Research Tool
author: jseals
version: 1.2.2
license: MIT
description: Native Open WebUI tool for Deep Research. Shows an inline selector UI for research depth and output type, then calls a LangGraph open_deep_research backend.
required_open_webui_version: 0.8.0
"""

import asyncio
import json
import re
import time
import html as html_lib
from typing import Optional, Callable, Awaitable

import aiohttp
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

RESEARCH_LEVELS = {
    "1": {
        "label": "Quick Scan",
        "emoji": "⚡",
        "time": "~1-2 min",
        "detail": "Brief overview",
        "suffix": " Provide a brief, concise overview. Keep it short — 2-3 paragraphs max.",
        "config": {
            "max_researcher_iterations": 1,
            "max_react_tool_calls": 2,
            "max_concurrent_research_units": 1,
        },
    },
    "2": {
        "label": "Standard",
        "emoji": "🔍",
        "time": "~3-5 min",
        "detail": "Thorough analysis",
        "suffix": " Provide a thorough analysis with key findings and cited sources.",
        "config": {
            "max_researcher_iterations": 2,
            "max_react_tool_calls": 3,
            "max_concurrent_research_units": 2,
        },
    },
    "3": {
        "label": "Deep Dive",
        "emoji": "🧬",
        "time": "~7-10 min",
        "detail": "Comprehensive report",
        "suffix": " Conduct comprehensive, in-depth research. Explore multiple angles, compare perspectives, and provide a detailed report with extensive citations.",
        "config": {
            "max_researcher_iterations": 3,
            "max_react_tool_calls": 4,
            "max_concurrent_research_units": 3,
        },
    },
}

LEVEL_ALIASES = {
    "1": "1",
    "2": "2",
    "3": "3",
    "quick": "1",
    "scan": "1",
    "quick scan": "1",
    "standard": "2",
    "normal": "2",
    "deep": "3",
    "dive": "3",
    "deep dive": "3",
}

OUTPUT_TYPES = {
    "executive_summary": {
        "label": "Executive Summary",
        "emoji": "📌",
        "detail": "Bottom-line takeaways",
    },
    "comparison_matrix": {
        "label": "Comparison Matrix",
        "emoji": "📊",
        "detail": "Criteria-by-option comparison",
    },
    "technical_brief": {
        "label": "Technical Brief",
        "emoji": "🛠️",
        "detail": "Detailed technical findings",
    },
    "recommendation_memo": {
        "label": "Recommendation Memo",
        "emoji": "✅",
        "detail": "Recommendation with rationale",
    },
}

OUTPUT_TYPE_ALIASES = {
    "executive_summary": "executive_summary",
    "executive summary": "executive_summary",
    "comparison_matrix": "comparison_matrix",
    "comparison matrix": "comparison_matrix",
    "technical_brief": "technical_brief",
    "technical brief": "technical_brief",
    "recommendation_memo": "recommendation_memo",
    "recommendation memo": "recommendation_memo",
}

NODE_STATUS = {
    "clarify_with_user": "Analyzing research request...",
    "write_research_brief": "📋 Writing research brief...",
    "research_supervisor": "🧠 Planning research strategy...",
    "final_report_generation": "✍️ Writing final report...",
}

THEME_CSS = """
:root {
  --color-text-primary: #1F2937;
  --color-text-secondary: #6B7280;
  --color-bg-primary: #FFFFFF;
  --color-bg-secondary: #F9FAFB;
  --color-border-tertiary: rgba(0,0,0,0.15);
  --color-border-secondary: rgba(0,0,0,0.30);
  --color-accent: rgba(59,130,246,0.95);
  --color-accent-soft: rgba(59,130,246,0.10);
  --font-sans: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
}
:root[data-theme="dark"] {
  --color-text-primary: #E5E7EB;
  --color-text-secondary: #9CA3AF;
  --color-bg-primary: #111827;
  --color-bg-secondary: #1F2937;
  --color-border-tertiary: rgba(255,255,255,0.15);
  --color-border-secondary: rgba(255,255,255,0.30);
  --color-accent: rgba(96,165,250,0.98);
  --color-accent-soft: rgba(96,165,250,0.14);
}
"""

THEME_DETECT = """<script>
(function(){
  function isDark(root){
    try {
      return root.classList.contains('dark') ||
             root.getAttribute('data-theme') === 'dark' ||
             getComputedStyle(root).colorScheme === 'dark';
    } catch (e) {
      return false;
    }
  }
  function apply(v){ document.documentElement.setAttribute('data-theme', v ? 'dark' : 'light'); }
  try {
    var parentRoot = parent.document.documentElement;
    apply(isDark(parentRoot));
    new MutationObserver(function(){ apply(isDark(parentRoot)); })
      .observe(parentRoot, { attributes: true, attributeFilter: ['class', 'data-theme', 'style'] });
  } catch (e) {
    var mq = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)');
    if (mq) {
      apply(mq.matches);
      mq.addEventListener('change', function(evt){ apply(evt.matches); });
    }
  }
})();
</script>"""

BODY_SCRIPTS = """<script>
let selectedLevel = null;
let selectedOutput = null;
let submitted = false;

function reportHeight(){
  try {
    var b = document.body;
    b.style.height = '0';
    var h = b.scrollHeight;
    b.style.height = '';
    parent.postMessage({type:'iframe:height', height:h}, '*');
  } catch (e) {}
}

function updateSelectionGroup(group, selectedKey){
  document.querySelectorAll('[data-group="' + group + '"]').forEach(function(el){
    const active = el.getAttribute('data-value') === selectedKey;
    el.setAttribute('data-active', active ? 'true' : 'false');
  });
}

function disableSelectionControls(){
  document.querySelectorAll('.card, .pill').forEach(function(el){
    el.disabled = true;
    el.style.cursor = 'default';
    el.style.transform = 'none';
    el.style.boxShadow = 'none';
    el.style.opacity = '0.68';
  });
}

function markSubmittedState(){
  const btn = document.getElementById('submit-btn');
  const hint = document.getElementById('selection-hint');
  submitted = true;
  disableSelectionControls();
  btn.disabled = true;
  btn.textContent = 'Research Submitted';
  btn.style.opacity = '0.92';
  btn.style.cursor = 'default';
  hint.textContent = 'Deep Research submitted. Send a new chat message to start another research request.';
  reportHeight();
}

function updateSubmitState(){
  const btn = document.getElementById('submit-btn');
  const hint = document.getElementById('selection-hint');

  if (submitted) {
    btn.disabled = true;
    btn.textContent = 'Research Submitted';
    btn.style.opacity = '0.92';
    btn.style.cursor = 'default';
    hint.textContent = 'Deep Research submitted. Send a new chat message to start another research request.';
    return;
  }

  const ready = !!selectedLevel && !!selectedOutput;
  btn.disabled = !ready;
  btn.textContent = 'Run Deep Research';
  btn.style.opacity = ready ? '1' : '0.55';
  btn.style.cursor = ready ? 'pointer' : 'not-allowed';

  if (!selectedLevel && !selectedOutput) {
    hint.textContent = 'Select a research depth and output type.';
  } else if (!selectedLevel) {
    hint.textContent = 'Select a research depth.';
  } else if (!selectedOutput) {
    hint.textContent = 'Select an output type.';
  } else {
    hint.textContent = 'Ready to run deep research.';
  }
}

function selectLevel(value){
  if (submitted) return;
  selectedLevel = value;
  updateSelectionGroup('level', value);
  updateSubmitState();
}

function selectOutput(value){
  if (submitted) return;
  selectedOutput = value;
  updateSelectionGroup('output', value);
  updateSubmitState();
}

function sendPrompt(text){
  try {
    parent.postMessage({type:'input:prompt:submit', text:text}, '*');
  } catch (e) {}
}

function submitResearch(){
  if (submitted || !selectedLevel || !selectedOutput) return;
  const query = document.body.getAttribute('data-query') || 'Research topic';
  const prompt = 'Run deep research level ' + selectedLevel + ' output ' + selectedOutput + ' on: ' + query;
  markSubmittedState();
  sendPrompt(prompt);
}

window.addEventListener('load', function(){
  reportHeight();
  updateSubmitState();
});
window.addEventListener('resize', reportHeight);
try { new ResizeObserver(reportHeight).observe(document.body); } catch (e) {}
</script>"""

BASE_CSS = """
* { box-sizing: border-box; margin: 0; font-family: var(--font-sans); }
html, body { overflow: hidden; }
body {
  background: transparent;
  color: var(--color-text-primary);
  line-height: 1.5;
  padding: 0;
}
button { color: inherit; }
.card {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 16px 12px;
  border-radius: 12px;
  border: 1px solid var(--color-border-tertiary);
  background: transparent;
  cursor: pointer;
  text-align: center;
  font-size: 13px;
  transition: all 0.15s ease;
}
.card:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.10);
  background: rgba(128,128,128,0.06);
}
.card[data-active="true"] {
  border-color: var(--color-accent);
  background: var(--color-accent-soft);
}
.card:disabled,
.pill:disabled {
  pointer-events: none;
}
.pill {
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--color-border-tertiary);
  background: transparent;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  text-align: left;
  transition: all 0.15s ease;
}
.pill:hover:not(:disabled) {
  background: rgba(128,128,128,0.06);
}
.pill[data-active="true"] {
  border-color: var(--color-accent);
  background: var(--color-accent-soft);
}
.submit-btn {
  width: 100%;
  border: none;
  border-radius: 12px;
  padding: 12px 14px;
  font-size: 14px;
  font-weight: 700;
  background: var(--color-accent);
  color: white;
}
.submit-btn:disabled {
  pointer-events: none;
}
"""


def _wrap_html(content: str, query: str) -> str:
    q_safe = html_lib.escape(query, quote=True)
    return (
        "<!DOCTYPE html><html><head>"
        f"<style>{THEME_CSS}\n{BASE_CSS}</style>{THEME_DETECT}"
        "</head>"
        f'<body data-query="{q_safe}">'
        f"{content}{BODY_SCRIPTS}</body></html>"
    )


def _selector_html(query: str) -> str:
    q_display = html_lib.escape(query if len(query) <= 140 else query[:137] + "...")

    level_cards = []
    for key, cfg in RESEARCH_LEVELS.items():
        recommended = key == "2"
        badge = (
            '<div style="font-size:10px;font-weight:600;color:var(--color-accent);margin-top:6px">★ Recommended</div>'
            if recommended
            else ""
        )
        level_cards.append(
            f"""<button class="card" data-group="level" data-value="{key}" data-active="false" onclick="selectLevel('{key}')">
<span style="font-size:30px;line-height:1">{cfg['emoji']}</span>
<div style="font-weight:700;font-size:14px">{cfg['label']}</div>
<div style="opacity:0.68;font-size:11px;line-height:1.3">{cfg['time']}<br>{cfg['detail']}</div>
{badge}
</button>"""
        )

    output_pills = []
    for key, cfg in OUTPUT_TYPES.items():
        output_pills.append(
            f"""<button class="pill" data-group="output" data-value="{key}" data-active="false" onclick="selectOutput('{key}')">
<div style="display:flex;align-items:center;gap:8px"><span>{cfg['emoji']}</span><span>{cfg['label']}</span></div>
<div style="opacity:0.70;font-size:11px;font-weight:500;margin-top:4px">{cfg['detail']}</div>
</button>"""
        )

    return f"""
<div style="border-radius:16px;overflow:hidden;background:rgba(128,128,128,0.03);border:1px solid var(--color-border-tertiary)">
  <div style="padding:16px 20px;border-bottom:1px solid rgba(128,128,128,0.08);display:flex;align-items:center;gap:10px">
    <span style="font-size:22px">🔬</span>
    <div>
      <div style="font-size:15px;font-weight:700">Deep Research</div>
      <div style="font-size:12px;opacity:0.60;margin-top:2px">{q_display}</div>
    </div>
  </div>

  <div style="padding:14px 16px 10px 16px">
    <div style="font-size:12px;font-weight:700;letter-spacing:0.02em;text-transform:uppercase;opacity:0.72;margin-bottom:8px">1. Research depth</div>
    <div style="display:flex;gap:10px">{''.join(level_cards)}</div>
  </div>

  <div style="padding:8px 16px 10px 16px">
    <div style="font-size:12px;font-weight:700;letter-spacing:0.02em;text-transform:uppercase;opacity:0.72;margin-bottom:8px">2. Output type</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">{''.join(output_pills)}</div>
  </div>

  <div style="padding:12px 16px 16px 16px">
    <div id="selection-hint" style="font-size:12px;opacity:0.62;margin-bottom:10px">Select a research depth and output type.</div>
    <button id="submit-btn" class="submit-btn" onclick="submitResearch()" disabled>Run Deep Research</button>
  </div>
</div>
"""


class Tools:
    class Valves(BaseModel):
        LANGGRAPH_URL: str = Field(
            default="http://deep-research:2024",
            description="LangGraph open_deep_research API base URL",
        )
        REQUEST_TIMEOUT: int = Field(
            default=720, description="Research timeout in seconds"
        )
        MAX_QUERY_LENGTH: int = Field(default=4000, description="Maximum query length")
        DEFAULT_LEVEL: str = Field(
            default="2", description="Default level if an invalid level is received"
        )
        DEFAULT_OUTPUT_TYPE: str = Field(
            default="executive_summary",
            description="Default output type if an invalid output type is received",
        )
        RESEARCH_MODEL: str = Field(
            default="azure_openai:gpt-5.3-chat",
            description="Model for conducting research",
        )
        SUMMARIZATION_MODEL: str = Field(
            default="azure_openai:gpt-5.3-chat",
            description="Model for summarizing search results",
        )
        COMPRESSION_MODEL: str = Field(
            default="azure_openai:gpt-5.3-chat",
            description="Model for compressing research findings",
        )
        FINAL_REPORT_MODEL: str = Field(
            default="azure_openai:gpt-5.3-chat",
            description="Model for writing the final report",
        )
        SEARCH_API: str = Field(
            default="tavily",
            description="Search API to use (tavily, openai, anthropic, none)",
        )

    def __init__(self):
        self.valves = self.Valves()

    def show_research_options(self, query: str) -> HTMLResponse:
        """
        Show the Deep Research selector UI for a topic.

        Use this first when the user asks to research, investigate, compare,
        or deeply analyze a topic and has not yet picked both a depth and an output type.
        After the user clicks submit, they will send a message like:
        'Run deep research level 2 output comparison_matrix on: <their query>'
        Then call run_deep_research with that query, level, and output_type.
        """
        query = (query or "").strip()
        if not query:
            query = "Research topic"
        return HTMLResponse(
            content=_wrap_html(_selector_html(query), query),
            headers={"Content-Disposition": "inline"},
        )

    async def run_deep_research(
        self,
        query: str,
        level: int = 2,
        output_type: str = "executive_summary",
        __event_emitter__: Optional[Callable[[dict], Awaitable[None]]] = None,
        __event_call__: Optional[Callable[[dict], Awaitable[dict]]] = None,
    ) -> str:
        """
        Run Deep Research against the LangGraph backend.

        Call this when the user has already selected both a research depth
        and an output type, or when the user message begins with:
        'Run deep research level N output OUTPUT_TYPE on: ...'

        Arguments:
        - query: the topic to research
        - level: 1=Quick Scan, 2=Standard, 3=Deep Dive
        - output_type: executive_summary, comparison_matrix, technical_brief, recommendation_memo
        """
        emitter = __event_emitter__

        parsed_level, parsed_output_type, parsed_query = (
            self._extract_embedded_selection(query)
        )
        if parsed_query:
            query = parsed_query
            if parsed_level is not None:
                level = parsed_level
            if parsed_output_type:
                output_type = parsed_output_type

        query = (query or "").strip()
        if not query:
            return "❌ No research query provided."
        if len(query) > self.valves.MAX_QUERY_LENGTH:
            return f"❌ Query too long. Maximum is {self.valves.MAX_QUERY_LENGTH} characters."

        level_key = self._normalize_level(level)
        level_cfg = RESEARCH_LEVELS[level_key]
        label = level_cfg["label"]
        emoji = level_cfg["emoji"]
        output_key = self._normalize_output_type(output_type)
        output_cfg = OUTPUT_TYPES[output_key]

        research_prompt = query + level_cfg["suffix"]

        start_time = time.time()
        await self._emit_status(
            emitter,
            f"{emoji} Starting {label} for {output_cfg['label']}...",
            done=False,
        )

        url = self.valves.LANGGRAPH_URL.rstrip("/") + "/runs/stream"
        payload = {
            "assistant_id": "Deep Researcher",
            "input": {"messages": [{"role": "user", "content": research_prompt}]},
            "stream_mode": "updates",
            "config": {
                "configurable": {
                    "allow_clarification": False,
                    "research_model": self.valves.RESEARCH_MODEL,
                    "summarization_model": self.valves.SUMMARIZATION_MODEL,
                    "compression_model": self.valves.COMPRESSION_MODEL,
                    "final_report_model": self.valves.FINAL_REPORT_MODEL,
                    "search_api": self._normalize_search_api(self.valves.SEARCH_API),
                    **level_cfg["config"],
                }
            },
        }

        final_report = ""
        sources = []
        error_msg = None

        try:
            timeout = aiohttp.ClientTimeout(total=self.valves.REQUEST_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        await self._emit_status(emitter, "", done=True)
                        snippet = body[:300] if body else ""
                        return f"❌ LangGraph API returned HTTP {resp.status}. {snippet}".strip()

                    event_type = None
                    buf = b""

                    async for chunk in resp.content.iter_any():
                        buf += chunk
                        while b"\n" in buf:
                            line_bytes, buf = buf.split(b"\n", 1)
                            line = line_bytes.decode("utf-8", errors="ignore").strip()
                            if not line:
                                continue

                            if line.startswith("event: "):
                                event_type = line[7:].strip()
                                continue

                            if not line.startswith("data: ") or not event_type:
                                continue

                            try:
                                data = json.loads(line[6:])
                            except json.JSONDecodeError:
                                event_type = None
                                continue

                            elapsed = int(time.time() - start_time)

                            if event_type == "updates" and isinstance(data, dict):
                                for node_name, node_data in data.items():
                                    status_msg = NODE_STATUS.get(node_name)
                                    if status_msg:
                                        await self._emit_status(
                                            emitter, f"{status_msg} ({elapsed}s)"
                                        )

                                    if node_name == "research_supervisor":
                                        await self._emit_status(
                                            emitter,
                                            f"🔍 Research agents searching and analyzing... ({elapsed}s)",
                                        )

                                    if isinstance(node_data, dict):
                                        report = node_data.get("final_report")
                                        if report:
                                            final_report = report

                                        raw_notes = node_data.get("raw_notes", [])
                                        for note in raw_notes:
                                            if isinstance(note, str):
                                                self._extract_urls(note, sources)

                            elif event_type == "error":
                                error_msg = (
                                    json.dumps(data)
                                    if isinstance(data, dict)
                                    else str(data)
                                )

                            event_type = None

        except asyncio.TimeoutError:
            await self._emit_status(emitter, "", done=True)
            return f"❌ Research timed out after {round(time.time() - start_time)}s."
        except Exception as exc:
            await self._emit_status(emitter, "", done=True)
            return f"❌ Error while calling LangGraph backend: {exc}"

        await self._emit_status(emitter, "", done=True)

        if error_msg:
            return f"❌ Research error: {error_msg}"

        if not final_report:
            return "❌ Research completed but no report was generated."

        self._extract_urls(final_report, sources)
        deduped_urls = []
        seen = set()
        for url_item in sources:
            if url_item and url_item not in seen:
                seen.add(url_item)
                deduped_urls.append(url_item)

        for url_item in deduped_urls:
            await self._emit_citation(emitter, url_item)

        elapsed = round(time.time() - start_time, 1)
        return self._build_result_package(
            query=query,
            level_key=level_key,
            output_key=output_key,
            elapsed=elapsed,
            visited_urls=deduped_urls,
            final_report=final_report,
        )

    def _normalize_level(self, level) -> str:
        raw = str(level).strip().lower()
        return LEVEL_ALIASES.get(raw, self.valves.DEFAULT_LEVEL)

    def _normalize_output_type(self, output_type: str) -> str:
        raw = str(output_type or "").strip().lower()
        return OUTPUT_TYPE_ALIASES.get(raw, self.valves.DEFAULT_OUTPUT_TYPE)

    def _normalize_search_api(self, search_api: str) -> str:
        raw = str(search_api or "").strip().lower()
        allowed = {"tavily", "openai", "anthropic", "none"}
        return raw if raw in allowed else "tavily"

    def _extract_embedded_selection(
        self, query: str
    ) -> tuple[Optional[int], Optional[str], Optional[str]]:
        if not query:
            return None, None, None

        pattern = re.compile(
            r"^run\s+deep\s+research\s+level\s+(?P<level>\d+)\s+output\s+(?P<output>[a-zA-Z_ ]+)\s+on:\s*(?P<query>.+)$",
            re.IGNORECASE | re.DOTALL,
        )
        match = pattern.match(query.strip())
        if not match:
            return None, None, None

        level_str = match.group("level").strip()
        output_raw = match.group("output").strip()
        cleaned_query = match.group("query").strip()

        try:
            level_val = int(level_str)
        except ValueError:
            level_val = None

        return level_val, self._normalize_output_type(output_raw), cleaned_query

    def _extract_urls(self, text: str, url_list: list):
        urls = re.findall(r'https?://[^\s\)"\'<>]+', text)
        for url_item in urls:
            url_item = url_item.rstrip(".,;:)")
            if url_item not in url_list:
                url_list.append(url_item)

    async def _emit_status(self, emitter, description: str, done: bool = False):
        if emitter:
            await emitter(
                {
                    "type": "status",
                    "data": {
                        "description": description,
                        "done": done,
                        "hidden": False,
                    },
                }
            )

    async def _emit_citation(self, emitter, url: str, title: str = ""):
        if emitter and url:
            await emitter(
                {
                    "type": "source",
                    "data": {
                        "document": [title or url],
                        "metadata": [{"source": url, "name": title or url}],
                        "source": {"name": title or url, "url": url},
                    },
                }
            )

    def _build_result_package(
        self,
        *,
        query: str,
        level_key: str,
        output_key: str,
        elapsed: float,
        visited_urls: list,
        final_report: str,
    ) -> str:
        package = {
            "query": query,
            "level": {
                "key": level_key,
                "label": RESEARCH_LEVELS[level_key]["label"],
                "emoji": RESEARCH_LEVELS[level_key]["emoji"],
            },
            "output_type": {
                "key": output_key,
                "label": OUTPUT_TYPES[output_key]["label"],
                "emoji": OUTPUT_TYPES[output_key]["emoji"],
            },
            "elapsed_seconds": elapsed,
            "source_count": len(visited_urls),
            "sources": visited_urls,
            "research_report_markdown": final_report.strip(),
        }
        return json.dumps(package, ensure_ascii=False)
