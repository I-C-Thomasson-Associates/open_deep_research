"""
title: Deep Research Tool
author: jseals
version: 1.7.2
license: MIT
description: Native Open WebUI tool for Deep Research. Shows an inline selector UI for research depth and output type, then calls a LangGraph open_deep_research backend. Branded with Salas O'Brien primary color palette.
required_open_webui_version: 0.8.0
"""

import asyncio
import hashlib
import json
import re
import threading
import time
import html as html_lib
from urllib.parse import urlparse, urlunparse
from typing import Optional, Callable, Awaitable, Any
import aiohttp
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# ─────────────────────────────────────────────
# Configuration constants
# ─────────────────────────────────────────────
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
        "suffix": (
            " Provide a thorough analysis with key findings and cited sources. "
            "Cover both technical developments and their practical/commercial implications. "
            "Include specific examples, named entities, and dates where available."
        ),
        "config": {
            "max_researcher_iterations": 3,
            "max_react_tool_calls": 4,
            "max_concurrent_research_units": 2,
        },
    },
    "3": {
        "label": "Deep Dive",
        "emoji": "🧬",
        "time": "~7-10 min",
        "detail": "Comprehensive report",
        "suffix": (
            " Conduct comprehensive, in-depth research. For each major topic or finding, "
            "investigate: (1) the technical mechanisms and how they work, "
            "(2) the commercial products, companies, and ecosystem that resulted, "
            "(3) specific failures, discontinued projects, or notable incidents, "
            "(4) economic or societal impact with concrete figures where available, "
            "(5) regulatory or governance responses, "
            "(6) practical deployment considerations including cost, infrastructure, and tooling. "
            "Explore multiple angles, include primary sources (papers, official announcements, standards), "
            "and provide extensive citations."
        ),
        "config": {
            "max_researcher_iterations": 5,
            "max_react_tool_calls": 6,
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
    "custom": {
        "label": "Custom",
        "emoji": "✏️",
        "detail": "Specify your own format",
    },
}

OUTPUT_TYPE_ALIASES = {
    "executive_summary": "executive_summary",
    "executive summary": "executive_summary",
    "comparison_matrix": "comparison_matrix",
    "comparison matrix": "comparison_matrix",
    "technical_brief": "technical_brief",
    "technical brief": "technical_brief",
    "custom": "custom",
    "other": "custom",
}

NODE_STATUS = {
    "clarify_with_user": ("🔎", "Analyzing research request"),
    "write_research_brief": ("📋", "Planning"),
    "research_supervisor": ("🧠", "Researching"),
    "research_team": ("🔬", "Research agents searching & analyzing"),
    "final_report_generation": ("✍️", "Generating final report"),
}

RUN_LOCATION_PATTERN = re.compile(
    r"(?:/threads/(?P<thread_id>[^/?#]+))?/runs/(?P<run_id>[^/?#]+)"
)

URL_PATTERN = re.compile(r'https?://[^\s\)"\'<>]+', re.IGNORECASE)

LOW_TRUST_DOMAINS = {
    "facebook.com",
    "reddit.com",
    "x.com",
    "twitter.com",
    "youtube.com",
    "tiktok.com",
    "medium.com",
    "substack.com",
    "blogspot.com",
    "wordpress.com",
    "quora.com",
    "pinterest.com",
}

PRIMARY_SOURCE_HINTS = {
    "arxiv.org",
    "openreview.net",
    "aclanthology.org",
    "nature.com",
    "science.org",
    "springer.com",
    "cell.com",
    "nejm.org",
    "who.int",
    "nih.gov",
    "nist.gov",
    "census.gov",
    "sec.gov",
    "europa.eu",
    "openai.com",
    "anthropic.com",
    "google.com",
    "microsoft.com",
    "meta.com",
    "deepmind.com",
    "github.com",
    "ietf.org",
    "iso.org",
}

# ─────────────────────────────────────────────
# Salas O'Brien branded theme
# Primary palette: Impact Blue, Reflex Blue,
# Black, Grays 1-5, White
# Font: Arial (general use)
# ─────────────────────────────────────────────
THEME_CSS = """
:root {
  --sob-impact-blue: #009DE0;
  --sob-reflex-blue: #000086;
  --sob-black: #000000;
  --sob-gray1: #333333;
  --sob-gray2: #666666;
  --sob-gray3: #999999;
  --sob-gray4: #CCCCCC;
  --sob-gray5: #EDEDED;
  --sob-white: #FFFFFF;
  --color-text-primary: var(--sob-gray1);
  --color-text-secondary: var(--sob-gray2);
  --color-text-tertiary: var(--sob-gray3);
  --color-bg-primary: var(--sob-white);
  --color-bg-card: var(--sob-gray5);
  --color-border: var(--sob-gray4);
  --color-border-active: var(--sob-impact-blue);
  --color-accent: var(--sob-impact-blue);
  --color-accent-hover: var(--sob-reflex-blue);
  --color-accent-soft: rgba(0, 157, 224, 0.10);
  --color-accent-text: var(--sob-white);
  --color-recommended: var(--sob-impact-blue);
  --font-brand: Arial, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
}
:root[data-theme="dark"] {
  --color-text-primary: var(--sob-gray5);
  --color-text-secondary: var(--sob-gray3);
  --color-text-tertiary: var(--sob-gray2);
  --color-bg-primary: #111111;
  --color-bg-card: var(--sob-gray1);
  --color-border: var(--sob-gray2);
  --color-border-active: var(--sob-impact-blue);
  --color-accent: var(--sob-impact-blue);
  --color-accent-hover: #33B1E6;
  --color-accent-soft: rgba(0, 157, 224, 0.15);
  --color-accent-text: var(--sob-white);
  --color-recommended: var(--sob-impact-blue);
}
"""

THEME_DETECT = """<script>
(function(){
  function apply(v){ document.documentElement.setAttribute('data-theme', v ? 'dark' : 'light'); }
  
  // Strategy: check if we're in a dark context by probing actual rendered colors
  // Open WebUI may inject styles that affect the iframe
  function detectFromContext(){
    // Create a probe element that inherits from the page context
    var probe = document.createElement('div');
    probe.style.cssText = 'position:absolute;visibility:hidden;width:0;height:0;';
    document.documentElement.appendChild(probe);
    var bg = getComputedStyle(probe).backgroundColor;
    document.documentElement.removeChild(probe);
    
    // Check if the iframe itself has a dark background set by the parent
    var bodyBg = getComputedStyle(document.body || document.documentElement).backgroundColor;
    if(bodyBg && bodyBg !== 'rgba(0, 0, 0, 0)'){
      var m = bodyBg.match(/\\d+/g);
      if(m && m.length >= 3){
        var lum = (parseInt(m[0])*299 + parseInt(m[1])*587 + parseInt(m[2])*114) / 1000;
        return lum < 128;
      }
    }
    
    // Fallback: use prefers-color-scheme
    if(window.matchMedia){
      return window.matchMedia('(prefers-color-scheme: dark)').matches;
    }
    return false;
  }
  
  // Try parent access first (works when not sandboxed)
  try {
    var pr = parent.document.documentElement;
    apply(pr.classList.contains('dark'));
    new MutationObserver(function(){
      apply(pr.classList.contains('dark'));
    }).observe(pr, { attributes:true, attributeFilter:['class'] });
  } catch(e){
    // Sandboxed iframe - detect from context
    if(document.body){
      apply(detectFromContext());
    } else {
      document.addEventListener('DOMContentLoaded', function(){ apply(detectFromContext()); });
    }
    // Also listen for OS theme changes
    if(window.matchMedia){
      var mq = window.matchMedia('(prefers-color-scheme: dark)');
      mq.addEventListener('change', function(evt){ apply(evt.matches); });
    }
  }
})();
</script>"""

BODY_SCRIPTS = """<script>
let selectedLevel = null;
let selectedOutput = null;
let customFormat = '';
let submitted = false;

function reportHeight(){
  try {
    var b = document.body;
    b.style.height = '0';
    var h = b.scrollHeight;
    b.style.height = '';
    parent.postMessage({type:'iframe:height', height:h}, '*');
  } catch(e){}
}

function updateSelectionGroup(group, selectedKey){
  document.querySelectorAll('[data-group="'+group+'"]').forEach(function(el){
    el.setAttribute('data-active', el.getAttribute('data-value') === selectedKey ? 'true' : 'false');
  });
}

function disableAll(){
  document.querySelectorAll('.card, .pill').forEach(function(el){
    el.disabled = true;
    el.style.cursor = 'default';
    el.style.transform = 'none';
    el.style.boxShadow = 'none';
    el.style.opacity = '0.55';
  });
  var ci = document.getElementById('custom-input');
  if(ci){ ci.disabled = true; ci.style.opacity = '0.55'; }
}

function markSubmitted(){
  var btn = document.getElementById('submit-btn');
  var hint = document.getElementById('selection-hint');
  submitted = true;
  disableAll();
  btn.disabled = true;
  btn.textContent = '\\u2713 Research Submitted';
  btn.style.opacity = '0.85';
  btn.style.cursor = 'default';
  hint.textContent = 'Deep Research submitted. Send a new message to start another.';
  reportHeight();
}

function updateSubmitState(){
  var btn = document.getElementById('submit-btn');
  var hint = document.getElementById('selection-hint');
  if(submitted){ return; }

  var outputReady = !!selectedOutput && (selectedOutput !== 'custom' || customFormat.trim().length > 0);
  var ready = !!selectedLevel && outputReady;

  btn.disabled = !ready;
  btn.style.opacity = ready ? '1' : '0.45';
  btn.style.cursor = ready ? 'pointer' : 'not-allowed';
  btn.textContent = 'Run Deep Research';

  if(!selectedLevel && !selectedOutput) hint.textContent = 'Select a research depth and output type.';
  else if(!selectedLevel) hint.textContent = 'Select a research depth.';
  else if(selectedOutput === 'custom' && !customFormat.trim()) hint.textContent = 'Describe your desired output format.';
  else if(!selectedOutput) hint.textContent = 'Select an output type.';
  else hint.textContent = 'Ready \\u2014 click below to begin.';
}

function selectLevel(v){
  if(!submitted){ selectedLevel=v; updateSelectionGroup('level',v); updateSubmitState(); }
}

function selectOutput(v){
  if(submitted) return;
  selectedOutput = v;
  updateSelectionGroup('output', v);

  var wrap = document.getElementById('custom-input-wrap');
  if(v === 'custom'){
    wrap.setAttribute('data-visible', 'true');
    var ci = document.getElementById('custom-input');
    if(ci) ci.focus();
  } else {
    wrap.setAttribute('data-visible', 'false');
  }
  updateSubmitState();
  reportHeight();
}

function onCustomInput(el){
  customFormat = el.value;
  updateSubmitState();
}

function submitResearch(){
  if(submitted || !selectedLevel || !selectedOutput) return;
  var query = (typeof window.__deepResearchOriginalQuery === 'string')
    ? window.__deepResearchOriginalQuery
    : (document.body.getAttribute('data-query') || 'Research topic');
  var outputVal = selectedOutput;
  if(selectedOutput === 'custom' && customFormat.trim()){
    outputVal = 'custom:' + customFormat.trim();
  }
  var prompt = 'Run deep research level '+selectedLevel+' output '+outputVal+' on: '+query;
  markSubmitted();
  try { parent.postMessage({type:'input:prompt:submit', text:prompt}, '*'); } catch(e){}
}

window.addEventListener('load', function(){ reportHeight(); updateSubmitState(); });
window.addEventListener('resize', reportHeight);
try { new ResizeObserver(reportHeight).observe(document.body); } catch(e){}
</script>"""

BASE_CSS = """
* { box-sizing: border-box; margin: 0; font-family: var(--font-brand); }
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
  border: 1.5px solid var(--color-border);
  background: var(--color-bg-card);
  cursor: pointer;
  text-align: center;
  font-size: 13px;
  transition: border-color 0.15s ease, background 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease;
}
.card:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 14px rgba(0,0,0,0.08);
  border-color: var(--color-text-tertiary);
}
.card[data-active="true"] {
  border-color: var(--color-border-active);
  background: var(--color-accent-soft);
}
.card:disabled, .pill:disabled { pointer-events: none; }
.pill {
  padding: 10px 14px;
  border-radius: 10px;
  border: 1.5px solid var(--color-border);
  background: var(--color-bg-card);
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  text-align: left;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.pill:hover:not(:disabled) {
  border-color: var(--color-text-tertiary);
}
.pill[data-active="true"] {
  border-color: var(--color-border-active);
  background: var(--color-accent-soft);
}
.submit-btn {
  width: 100%;
  border: none;
  border-radius: 12px;
  padding: 13px 14px;
  font-size: 14px;
  font-weight: 700;
  background: var(--color-accent);
  color: var(--color-accent-text);
  letter-spacing: 0.01em;
  transition: background 0.15s ease;
}
.submit-btn:hover:not(:disabled) {
  background: var(--color-accent-hover);
}
.submit-btn:disabled { pointer-events: none; }
.section-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--color-text-secondary);
  margin-bottom: 8px;
}
.brand-slash {
  display: inline-block;
  width: 3px;
  height: 20px;
  background: var(--color-accent);
  transform: rotate(-45deg);
  margin-right: 10px;
  border-radius: 1px;
  flex-shrink: 0;
}
.custom-input-wrap {
  margin-top: 10px;
  display: none;
  animation: fadeIn 0.15s ease;
}
.custom-input-wrap[data-visible="true"] {
  display: block;
}
.custom-input {
  width: 100%;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1.5px solid var(--color-border);
  background: var(--color-bg-card);
  color: var(--color-text-primary);
  font-family: var(--font-brand);
  font-size: 13px;
  outline: none;
  transition: border-color 0.15s ease;
}
.custom-input:focus {
  border-color: var(--color-border-active);
}
.custom-input::placeholder {
  color: var(--color-text-tertiary);
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}
"""


def _wrap_html(content: str, query: str) -> str:
    q_safe = html_lib.escape(query, quote=True)
    q_json = json.dumps(query, ensure_ascii=False).replace("</", "<\\/")
    return (
        "<!DOCTYPE html><html><head>"
        f"<style>{THEME_CSS}\n{BASE_CSS}</style>{THEME_DETECT}"
        "</head>"
        f'<body data-query="{q_safe}">'
        f"<script>window.__deepResearchOriginalQuery = {q_json};</script>"
        f"{content}{BODY_SCRIPTS}</body></html>"
    )


def _selector_html(query: str) -> str:
    q_display = html_lib.escape(query)
    # Build level cards
    level_cards = []
    for key, cfg in RESEARCH_LEVELS.items():
        badge = ""
        if key == "2":
            badge = '<div style="font-size:10px;font-weight:700;color:var(--color-recommended);margin-top:6px">★ Recommended</div>'
        level_cards.append(
            f"""<button class="card" data-group="level" data-value="{key}" data-active="false" onclick="selectLevel('{key}')">
<span style="font-size:28px;line-height:1">{cfg['emoji']}</span>
<div style="font-weight:700;font-size:14px">{cfg['label']}</div>
<div style="color:var(--color-text-secondary);font-size:11px;line-height:1.3">{cfg['time']}<br>{cfg['detail']}</div>
{badge}
</button>"""
        )
    # Build output pills
    output_pills = []
    for key, cfg in OUTPUT_TYPES.items():
        output_pills.append(
            f"""<button class="pill" data-group="output" data-value="{key}" data-active="false" onclick="selectOutput('{key}')">
<div style="display:flex;align-items:center;gap:8px"><span>{cfg['emoji']}</span><span>{cfg['label']}</span></div>
<div style="color:var(--color-text-secondary);font-size:11px;font-weight:500;margin-top:4px">{cfg['detail']}</div>
</button>"""
        )
    return f"""
<div style="border-radius:16px;overflow:hidden;background:var(--color-bg-primary);border:1.5px solid var(--color-border)">
  <div style="padding:16px 20px;border-bottom:1.5px solid var(--color-border);display:flex;align-items:center;gap:4px">
    <span class="brand-slash"></span>
    <div>
      <div style="font-size:15px;font-weight:700;color:var(--color-text-primary)">Deep Research</div>
      <div style="font-size:12px;color:var(--color-text-secondary);margin-top:2px;white-space:pre-wrap;word-break:break-word;max-height:90px;overflow:auto">{q_display}</div>
    </div>
  </div>
  <div style="padding:14px 16px 10px 16px">
    <div class="section-label">1. Research depth</div>
    <div style="display:flex;gap:10px">{''.join(level_cards)}</div>
  </div>
  <div style="padding:8px 16px 10px 16px">
    <div class="section-label">2. Output type</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">{''.join(output_pills)}</div>
    <div id="custom-input-wrap" class="custom-input-wrap" data-visible="false">
      <input id="custom-input" class="custom-input" type="text" placeholder="e.g. SWOT analysis, pros/cons list, implementation roadmap…" maxlength="200" oninput="onCustomInput(this)">
    </div>
  </div>
  <div style="padding:12px 16px 16px 16px">
    <div id="selection-hint" style="font-size:12px;color:var(--color-text-secondary);margin-bottom:10px">Select a research depth and output type.</div>
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
            default=1800, description="Research timeout in seconds"
        )
        MAX_QUERY_LENGTH: int = Field(default=4000, description="Maximum query length")
        DEFAULT_LEVEL: str = Field(
            default="2", description="Default level if an invalid level is received"
        )
        DEFAULT_OUTPUT_TYPE: str = Field(
            default="executive_summary",
            description="Default output type if an invalid output type is received (does not apply to custom)",
        )
        RESEARCH_MODEL: str = Field(
            default="azure_openai:gpt-5.3-chat",
            description="Model for conducting research (ReAct agent)",
        )
        SUMMARIZATION_MODEL: str = Field(
            default="azure_openai:gpt-4.1-mini",
            description="Model for summarizing search results",
        )
        COMPRESSION_MODEL: str = Field(
            default="azure_openai:gpt-4.1-mini",
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
        ON_DISCONNECT: str = Field(
            default="continue",
            description="Run behavior when stream disconnects (continue or cancel)",
        )
        USE_THREADED_RUNS: bool = Field(
            default=True,
            description="Create per-request LangGraph threads for reliable join/cancel",
        )
        THREAD_TTL_MINUTES: int = Field(
            default=20,
            description="Thread TTL in minutes (0 disables TTL)",
        )
        JOIN_RETRY_ATTEMPTS: int = Field(
            default=6,
            description="Join retry attempts after stream disconnect",
        )
        JOIN_RETRY_DELAY_SECONDS: int = Field(
            default=2,
            description="Delay between join retries in seconds",
        )
        ENABLE_REQUEST_DEDUPE: bool = Field(
            default=True,
            description="Prevent duplicate run_deep_research executions for the same message",
        )
        DEDUPE_CACHE_TTL_SECONDS: int = Field(
            default=1800,
            description="Seconds to cache per-message results for duplicate tool calls",
        )
        STRICT_SOURCE_QUALITY: bool = Field(
            default=True,
            description="Enable strict source curation with trust filtering",
        )
        MAX_RETURNED_SOURCES: int = Field(
            default=40,
            description="Fallback maximum curated sources when level-specific caps are invalid",
        )
        MAX_RETURNED_SOURCES_LEVEL_1: int = Field(
            default=30,
            description="Maximum curated sources for Quick Scan (level 1)",
        )
        MAX_RETURNED_SOURCES_LEVEL_2: int = Field(
            default=100,
            description="Maximum curated sources for Standard (level 2)",
        )
        MAX_RETURNED_SOURCES_LEVEL_3: int = Field(
            default=250,
            description="Maximum curated sources for Deep Dive (level 3)",
        )
        MIN_PRIMARY_RATIO: float = Field(
            default=0.6,
            description="Minimum ratio of curated sources that should be primary/official",
        )
        ALLOW_LOW_TRUST_IF_NO_ALTERNATIVE: bool = Field(
            default=True,
            description="Allow limited low-trust sources when higher-quality alternatives are unavailable",
        )
        SHOW_QUEUE_POSITION: bool = Field(
            default=True,
            description="Show queue position to users when their run is waiting for a slot",
        )
        ENABLE_BACKEND_QUEUE_RANK: bool = Field(
            default=True,
            description="Use backend APIs to compute exact queue rank when available",
        )
        QUEUE_POLL_INTERVAL_SECONDS: int = Field(
            default=15,
            description="Seconds between queue position polls while waiting",
        )
        QUEUE_THREAD_SCAN_LIMIT: int = Field(
            default=200,
            description="Maximum busy threads to scan when computing exact queue rank",
        )

    def __init__(self):
        self.valves = self.Valves()
        self._request_registry: dict[str, dict[str, Any]] = {}
        self._request_registry_lock = threading.RLock()

    # ─────────────────────────────────────────
    # Selector UI
    # ─────────────────────────────────────────
    def show_research_options(
        self,
        query: str,
        __metadata__: Optional[dict] = None,
    ) -> HTMLResponse:
        """
        Show the Deep Research selector UI for a topic.
        Use this first when the user asks to research, investigate, compare,
        or deeply analyze a topic and has not yet picked both a depth and an output type.
        After the user clicks submit, they will send a message like:
        'Run deep research level 2 output comparison_matrix on: <their query>'
        Then call run_deep_research with that query, level, and output_type.
        """
        query = self._resolve_selector_query(query, __metadata__)
        return HTMLResponse(
            content=_wrap_html(_selector_html(query), query),
            headers={"Content-Disposition": "inline"},
        )

    # ─────────────────────────────────────────
    # Main research runner
    # ─────────────────────────────────────────
    async def run_deep_research(
        self,
        query: str,
        level: int = 2,
        output_type: str = "executive_summary",
        __event_emitter__: Optional[Callable[[dict], Awaitable[None]]] = None,
        __event_call__: Optional[Callable[[dict], Awaitable[dict]]] = None,
        __metadata__: Optional[dict] = None,
        __user__: Optional[dict] = None,
    ) -> str:
        """
        Run Deep Research against the LangGraph backend.
        Call this when the user has already selected both a research depth
        and an output type, or when the user message begins with:
        'Run deep research level N output OUTPUT_TYPE on: ...'
        Arguments:
        - query: the topic to research
        - level: 1=Quick Scan, 2=Standard, 3=Deep Dive
        - output_type: executive_summary, comparison_matrix, technical_brief, or custom:<description>
        """
        emit = __event_emitter__

        parsed_level, parsed_output_type, parsed_query = (
            self._extract_embedded_selection(query)
        )
        if parsed_query:
            query = parsed_query
            if parsed_level is not None:
                level = parsed_level
            if parsed_output_type:
                output_type = parsed_output_type

        if query is None:
            query = ""
        elif not isinstance(query, str):
            query = str(query)
        request_key: Optional[str] = None
        if not query.strip():
            return "❌ No research query provided."
        if len(query) > self.valves.MAX_QUERY_LENGTH:
            return f"❌ Query too long. Maximum is {self.valves.MAX_QUERY_LENGTH} characters."

        level_key = self._normalize_level(level)
        level_cfg = RESEARCH_LEVELS[level_key]

        output_key = self._normalize_output_type(output_type)

        if self.valves.ENABLE_REQUEST_DEDUPE:
            request_key = self._build_request_key(
                query=query,
                level_key=level_key,
                output_key=output_key,
                metadata=__metadata__,
                user=__user__,
            )
            dedupe_state, cached_result = self._begin_request(request_key)
            if dedupe_state == "active":
                await self._emit_status(
                    emit,
                    "⏳ Duplicate request ignored: research already in progress for this message.",
                    done=True,
                )
                return "⚠️ Duplicate request ignored: research is already running for this message."
            if dedupe_state == "reuse":
                await self._emit_status(
                    emit,
                    "♻️ Duplicate request ignored: reusing existing result for this message.",
                    done=True,
                )
                if cached_result:
                    return cached_result
                return "⚠️ Duplicate request ignored: a result for this message was already generated."

        if output_key.startswith("custom:"):
            custom_desc = output_key[7:].strip()
            output_cfg = {"label": custom_desc, "emoji": "✏️"}
            output_suffix = f" Format the output as: {custom_desc}."
        else:
            output_cfg = OUTPUT_TYPES[output_key]
            output_suffix = ""

        research_prompt = query + level_cfg["suffix"] + output_suffix
        start_time = time.time()

        # Defer the starting message — don't emit until we know
        # the run isn't queued (or after queue transition).
        _deferred_start_msg = (
            f"{level_cfg['emoji']} Starting {level_cfg['label']} research for {output_cfg['label']}…"
        )

        base_url = self.valves.LANGGRAPH_URL.rstrip("/")
        thread_id: Optional[str] = None
        run_id: Optional[str] = None

        if self.valves.USE_THREADED_RUNS:
            thread_id = await self._create_thread(base_url)

        if thread_id:
            url = f"{base_url}/threads/{thread_id}/runs/stream"
        else:
            url = f"{base_url}/runs/stream"

        payload = {
            "assistant_id": "Deep Researcher",
            "input": {"messages": [{"role": "user", "content": research_prompt}]},
            "stream_mode": ["updates", "values"],
            "on_disconnect": self._normalize_on_disconnect(self.valves.ON_DISCONNECT),
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
        evidence_ledger: list[dict[str, str]] = []
        error_msg = None
        stream_error_msg = None
        last_node = None

        # Queue detection state
        _first_real_event = False
        _queue_detected = False
        _queue_position: Optional[int] = None
        _initial_n_pending: Optional[int] = None
        _initial_position: Optional[int] = None
        _last_emitted_position: Optional[int] = None
        _last_queue_poll = 0.0
        _queue_keepalive_threshold = 5.0  # seconds of keepalives before declaring queued

        try:
            timeout = aiohttp.ClientTimeout(total=self.valves.REQUEST_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        snippet = body[:300] if body else ""
                        error_text = (
                            f"LangGraph API returned HTTP {resp.status}. {snippet}".strip()
                        )
                        await self._emit_status(emit, f"❌ {error_text}", done=True)
                        return self._finalize_result(
                            request_key,
                            f"❌ {error_text}",
                        )

                    header_run_id, header_thread_id = self._extract_run_metadata(
                        resp.headers.get("Content-Location")
                    )
                    if header_run_id:
                        run_id = header_run_id
                    if header_thread_id:
                        thread_id = header_thread_id

                    event_type = None
                    buf = b""

                    try:
                        async for chunk in resp.content.iter_any():
                            buf += chunk
                            while b"\n" in buf:
                                line_bytes, buf = buf.split(b"\n", 1)
                                line = line_bytes.decode(
                                    "utf-8", errors="ignore"
                                ).strip()
                                if not line:
                                    # Empty line = SSE keepalive while run is pending
                                    if (
                                        not _first_real_event
                                        and self.valves.SHOW_QUEUE_POSITION
                                        and (time.time() - start_time) > _queue_keepalive_threshold
                                    ):
                                        now = time.time()
                                        should_poll = (
                                            not _queue_detected
                                            or (now - _last_queue_poll) >= self.valves.QUEUE_POLL_INTERVAL_SECONDS
                                        )
                                        if should_poll:
                                            n_pending = await self._poll_queue_position(session, base_url)
                                            _last_queue_poll = now
                                            if n_pending is not None and n_pending > 0:
                                                was_queue_detected = _queue_detected
                                                _queue_detected = True
                                                exact_position = None
                                                if (
                                                    self.valves.ENABLE_BACKEND_QUEUE_RANK
                                                    and run_id
                                                ):
                                                    exact_position = (
                                                        await self._poll_exact_queue_position(
                                                            session=session,
                                                            base_url=base_url,
                                                            run_id=run_id,
                                                        )
                                                    )

                                                if exact_position is not None and exact_position > 0:
                                                    new_position = max(1, exact_position)
                                                else:
                                                    if (
                                                        not was_queue_detected
                                                        or _initial_n_pending is None
                                                        or _initial_position is None
                                                    ):
                                                        _initial_n_pending = n_pending
                                                        _initial_position = n_pending
                                                        new_position = _initial_position
                                                    else:
                                                        new_position = max(
                                                            1,
                                                            _initial_position - (_initial_n_pending - n_pending),
                                                        )

                                                if _queue_position is None:
                                                    _queue_position = new_position
                                                else:
                                                    _queue_position = min(
                                                        _queue_position or new_position,
                                                        new_position,
                                                    )
                                                # Only emit at milestone positions to keep
                                                # status history clean.  Milestones:
                                                # 10, 5, 4, 3, 2, 1  (and first detection)
                                                _is_milestone = (
                                                    _last_emitted_position is None  # first detection
                                                    or _queue_position <= 5  # every position <=5
                                                    or _queue_position % 5 == 0  # every 5 above that
                                                )
                                                _position_changed = (
                                                    _queue_position != _last_emitted_position
                                                )
                                                if _is_milestone and _position_changed:
                                                    if _queue_position <= 1:
                                                        await self._emit_status(
                                                            emit,
                                                            "⏳ You are #1 in line — starting soon",
                                                        )
                                                    else:
                                                        await self._emit_status(
                                                            emit,
                                                            f"⏳ You are #{_queue_position} in line",
                                                        )
                                                    _last_emitted_position = _queue_position
                                            elif n_pending == 0 and not _queue_detected:
                                                pass  # run started between creation and poll
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

                                if event_type == "metadata" and isinstance(data, dict):
                                    run_id = data.get("run_id") or run_id
                                    thread_id = data.get("thread_id") or thread_id
                                    # metadata fires immediately on stream open,
                                    # before the run starts executing — do NOT
                                    # count it as a real execution event.
                                    event_type = None
                                    continue

                                # Transition from queued to running —
                                # only on updates/values/error (not metadata)
                                if not _first_real_event:
                                    _first_real_event = True
                                    if _queue_detected:
                                        await self._emit_status(
                                            emit,
                                            "✅ Your research is starting now…",
                                        )
                                        # Reset timer so elapsed counts from
                                        # actual execution start, not submission.
                                        start_time = time.time()
                                    # Now emit the deferred starting message
                                    await self._emit_status(
                                        emit, _deferred_start_msg
                                    )

                                if event_type == "updates" and isinstance(data, dict):
                                    for node_name, node_data in data.items():
                                        if node_name != last_node:
                                            status_info = NODE_STATUS.get(node_name)
                                            if status_info:
                                                icon, label = status_info
                                                await self._emit_status(
                                                    emit,
                                                    f"{icon} {label}",
                                                )
                                            elif (
                                                node_name == "research_supervisor"
                                                or node_name.startswith("research")
                                            ):
                                                await self._emit_status(
                                                    emit,
                                                    "🔍 Researching",
                                                )
                                            last_node = node_name

                                        if isinstance(node_data, dict):
                                            report = node_data.get("final_report")
                                            if report:
                                                final_report = report
                                            evidence_ledger = self._merge_evidence_items(
                                                evidence_ledger,
                                                node_data.get("evidence_ledger"),
                                            )

                                elif event_type == "values" and isinstance(data, dict):
                                    report = self._extract_final_report(data)
                                    if report:
                                        final_report = report
                                    evidence_ledger = self._merge_evidence_items(
                                        evidence_ledger,
                                        self._extract_evidence_ledger_from_payload(data),
                                    )

                                elif event_type == "error":
                                    error_msg = (
                                        json.dumps(data)
                                        if isinstance(data, dict)
                                        else str(data)
                                    )

                                event_type = None

                    except asyncio.CancelledError:
                        raise
                    except Exception as stream_exc:
                        stream_error_msg = f"{type(stream_exc).__name__}: {stream_exc}"

                if not final_report and not error_msg and run_id:
                    await self._emit_status(
                        emit,
                        "🔄 Retrieving report…",
                    )
                    final_report = await self._join_for_final_report(
                        session=session,
                        base_url=base_url,
                        run_id=run_id,
                        thread_id=thread_id,
                        attempts=max(1, int(self.valves.JOIN_RETRY_ATTEMPTS)),
                        delay_seconds=max(1, int(self.valves.JOIN_RETRY_DELAY_SECONDS)),
                    )

        except asyncio.CancelledError:
            await asyncio.shield(self._cancel_run(base_url, run_id, thread_id))
            await self._emit_status(emit, "🛑 Research canceled", done=True)
            self._complete_request(request_key, "❌ Research canceled.")
            raise
        except asyncio.TimeoutError:
            await asyncio.shield(
                self._cancel_run_if_active(base_url, run_id, thread_id)
            )
            timeout_msg = f"Research timed out after {round(time.time() - start_time)}s."
            await self._emit_status(emit, f"❌ {timeout_msg}", done=True)
            return self._finalize_result(
                request_key,
                f"❌ {timeout_msg}",
            )
        except Exception as exc:
            await asyncio.shield(
                self._cancel_run_if_active(base_url, run_id, thread_id)
            )
            error_text = f"Error while calling LangGraph backend: {exc}"
            await self._emit_status(emit, f"❌ {error_text}", done=True)
            return self._finalize_result(
                request_key,
                f"❌ {error_text}",
            )

        if not final_report and stream_error_msg and not error_msg:
            await self._cancel_run_if_active(base_url, run_id, thread_id)
            error_msg = (
                f"Stream disconnected before report retrieval: {stream_error_msg}"
            )
        elif not final_report and not error_msg and run_id:
            run_status = await self._get_run_status(
                session=None,
                base_url=base_url,
                run_id=run_id,
                thread_id=thread_id,
            )
            if run_status == "timeout":
                error_msg = "Research timed out on the backend before generating a final report."
            elif run_status == "error":
                error_msg = "Research failed on the backend before generating a final report."
            elif run_status == "interrupted":
                error_msg = "Research was interrupted before generating a final report."
            elif run_status in {"pending", "running"}:
                await self._cancel_run_if_active(base_url, run_id, thread_id)
                error_msg = "Research did not finish cleanly before final report generation."
            elif run_status:
                error_msg = (
                    f"Research ended with status '{run_status}' before generating a final report."
                )
            else:
                await self._cancel_run_if_active(base_url, run_id, thread_id)
                error_msg = "Research completed but no report was generated."

        elapsed_final = round(time.time() - start_time, 1)

        if error_msg:
            await self._emit_status(emit, f"❌ {error_msg}", done=True)
            return self._finalize_result(request_key, f"❌ {error_msg}")
        if not final_report:
            msg = "Research completed but no report was generated."
            await self._emit_status(emit, f"❌ {msg}", done=True)
            return self._finalize_result(
                request_key,
                f"❌ {msg}",
            )

        await self._emit_status(
            emit,
            f"✅ Research complete — {elapsed_final}s",
            done=True,
        )

        curated_urls, source_quality = self._curate_sources(
            final_report,
            evidence_ledger,
            max_sources=self._max_sources_for_level(level_key),
            strict_mode=bool(self.valves.STRICT_SOURCE_QUALITY),
            min_primary_ratio=max(0.0, min(1.0, float(self.valves.MIN_PRIMARY_RATIO))),
            allow_low_trust_fallback=bool(self.valves.ALLOW_LOW_TRUST_IF_NO_ALTERNATIVE),
        )
        normalized_report = self._normalize_sources_section_markdown(
            final_report,
            curated_urls,
        )

        for u in curated_urls:
            await self._emit_citation(emit, u)

        return self._finalize_result(
            request_key,
            self._build_result_package(
                query=query,
                level_key=level_key,
                output_key=output_key,
                elapsed=elapsed_final,
                visited_urls=curated_urls,
                final_report=normalized_report,
                source_quality=source_quality,
            ),
        )

    # ─────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────
    def _resolve_selector_query(self, query: Any, metadata: Optional[dict]) -> str:
        query_from_arg = query if isinstance(query, str) else ("" if query is None else str(query))
        query_from_metadata = self._extract_query_from_metadata(metadata)

        if query_from_metadata.strip() and len(query_from_metadata.strip()) >= len(
            query_from_arg.strip()
        ):
            return query_from_metadata

        if query_from_arg:
            return query_from_arg
        if query_from_metadata:
            return query_from_metadata
        return "Research topic"

    def _extract_query_from_metadata(self, metadata: Optional[dict]) -> str:
        if not isinstance(metadata, dict):
            return ""

        candidates: list[str] = []

        def _append_candidate(value: Any):
            if isinstance(value, str) and value.strip():
                candidates.append(value)

        for key in ("query", "prompt", "message", "content"):
            _append_candidate(metadata.get(key))

        messages = metadata.get("messages")
        if isinstance(messages, list):
            for msg in reversed(messages):
                if not isinstance(msg, dict):
                    continue
                role = str(msg.get("role") or msg.get("type") or "").lower()
                if role not in {"user", "human"}:
                    continue

                content = msg.get("content")
                if isinstance(content, str):
                    _append_candidate(content)
                    break
                if isinstance(content, list):
                    text_parts: list[str] = []
                    for part in content:
                        if isinstance(part, dict):
                            text_val = part.get("text")
                            if isinstance(text_val, str) and text_val:
                                text_parts.append(text_val)
                    if text_parts:
                        candidates.append("".join(text_parts))
                        break

        if not candidates:
            return ""
        return max(candidates, key=len)

    def _normalize_level(self, level) -> str:
        raw = str(level).strip().lower()
        return LEVEL_ALIASES.get(raw, self.valves.DEFAULT_LEVEL)

    def _normalize_output_type(self, output_type: str) -> str:
        raw = str(output_type or "").strip().lower()
        if raw.startswith("custom:"):
            return output_type.strip()  # Preserve original case of the description
        return OUTPUT_TYPE_ALIASES.get(raw, self.valves.DEFAULT_OUTPUT_TYPE)

    def _normalize_search_api(self, search_api: str) -> str:
        raw = str(search_api or "").strip().lower()
        allowed = {"tavily", "openai", "anthropic", "none"}
        return raw if raw in allowed else "tavily"

    def _normalize_on_disconnect(self, value: str) -> str:
        raw = str(value or "").strip().lower()
        return raw if raw in {"continue", "cancel"} else "continue"

    def _max_sources_for_level(self, level_key: str) -> int:
        fallback = max(1, int(self.valves.MAX_RETURNED_SOURCES))
        by_level = {
            "1": max(1, int(self.valves.MAX_RETURNED_SOURCES_LEVEL_1)),
            "2": max(1, int(self.valves.MAX_RETURNED_SOURCES_LEVEL_2)),
            "3": max(1, int(self.valves.MAX_RETURNED_SOURCES_LEVEL_3)),
        }
        value = by_level.get(level_key, fallback)
        # Safety cap to prevent pathological payload sizes.
        return min(value, 400)

    def _build_request_key(
        self,
        *,
        query: str,
        level_key: str,
        output_key: str,
        metadata: Optional[dict],
        user: Optional[dict],
    ) -> str:
        chat_id = ""
        message_id = ""
        parent_message_id = ""
        user_id = ""

        if isinstance(metadata, dict):
            chat_id = str(metadata.get("chat_id") or "").strip()
            message_id = str(metadata.get("message_id") or "").strip()
            parent_message_id = str(metadata.get("parent_message_id") or "").strip()
            user_id = str(metadata.get("user_id") or "").strip()

        if not user_id and isinstance(user, dict):
            user_id = str(user.get("id") or user.get("user_id") or "").strip()

        if chat_id and parent_message_id:
            return f"chat:{chat_id}:parent:{parent_message_id}"
        if chat_id and message_id:
            return f"chat:{chat_id}:message:{message_id}"

        normalized_query = re.sub(r"\s+", " ", (query or "").strip()).lower()
        payload = "\n".join([normalized_query, level_key, output_key, chat_id, user_id])
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
        return f"fallback:{digest}"

    def _prune_request_registry(self, now: float):
        ttl = max(10, int(self.valves.DEDUPE_CACHE_TTL_SECONDS))
        stale_active_seconds = max(ttl * 2, int(self.valves.REQUEST_TIMEOUT) * 2, 300)
        to_delete: list[str] = []

        for key, entry in self._request_registry.items():
            state = str(entry.get("state") or "")
            started_at = float(entry.get("started_at") or 0)
            finished_at = float(entry.get("finished_at") or 0)

            if state == "completed" and finished_at and (now - finished_at) > ttl:
                to_delete.append(key)
            elif state == "active" and started_at and (now - started_at) > stale_active_seconds:
                to_delete.append(key)

        for key in to_delete:
            self._request_registry.pop(key, None)

    def _begin_request(self, request_key: str) -> tuple[str, Optional[str]]:
        now = time.time()
        with self._request_registry_lock:
            self._prune_request_registry(now)
            entry = self._request_registry.get(request_key)
            if entry:
                state = str(entry.get("state") or "")
                if state == "active":
                    return "active", None
                if state == "completed":
                    cached = entry.get("result")
                    if isinstance(cached, str) and cached:
                        return "reuse", cached
                    return "reuse", None

            self._request_registry[request_key] = {
                "state": "active",
                "started_at": now,
                "finished_at": None,
                "result": None,
            }
            return "accepted", None

    def _complete_request(self, request_key: Optional[str], result: str):
        if not request_key:
            return
        now = time.time()
        with self._request_registry_lock:
            entry = self._request_registry.get(request_key)
            if not entry:
                self._request_registry[request_key] = {
                    "state": "completed",
                    "started_at": now,
                    "finished_at": now,
                    "result": result,
                }
                return

            entry["state"] = "completed"
            entry["finished_at"] = now
            entry["result"] = result

    def _finalize_result(self, request_key: Optional[str], result: str) -> str:
        self._complete_request(request_key, result)
        return result

    def _extract_run_metadata(
        self, content_location: Optional[str]
    ) -> tuple[Optional[str], Optional[str]]:
        if not content_location:
            return None, None
        match = RUN_LOCATION_PATTERN.search(content_location)
        if not match:
            return None, None
        run_id = match.group("run_id")
        thread_id = match.group("thread_id")
        return run_id, thread_id

    async def _poll_queue_position(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
    ) -> Optional[int]:
        """Poll /metrics for current number of pending runs."""
        try:
            async with session.get(
                f"{base_url}/metrics",
                params={"format": "json"},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
                if not isinstance(data, dict):
                    return None
                queue_stats = data.get("queue")
                if not isinstance(queue_stats, dict):
                    return None
                n_pending = queue_stats.get("n_pending")
                if isinstance(n_pending, int):
                    return n_pending
                return None
        except Exception:
            return None

    def _is_terminal_run_status(self, status: Optional[str]) -> bool:
        return str(status or "").lower() in {"success", "error", "timeout", "interrupted"}

    async def _get_run_status(
        self,
        *,
        base_url: str,
        run_id: Optional[str],
        thread_id: Optional[str],
        session: Optional[aiohttp.ClientSession] = None,
    ) -> Optional[str]:
        if not run_id:
            return None

        owns_session = session is None
        active_session = session
        if owns_session:
            active_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )

        try:
            urls = []
            if thread_id:
                urls.append(f"{base_url}/threads/{thread_id}/runs/{run_id}")
            urls.append(f"{base_url}/runs/{run_id}")

            for run_url in urls:
                try:
                    async with active_session.get(
                        run_url, timeout=aiohttp.ClientTimeout(total=5)
                    ) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json(content_type=None)
                        if not isinstance(data, dict):
                            continue
                        status = data.get("status")
                        if isinstance(status, str) and status:
                            return status.lower()
                except Exception:
                    continue
            return None
        finally:
            if owns_session and active_session:
                await active_session.close()

    async def _cancel_run_if_active(
        self, base_url: str, run_id: Optional[str], thread_id: Optional[str]
    ) -> bool:
        status = await self._get_run_status(
            base_url=base_url,
            run_id=run_id,
            thread_id=thread_id,
        )
        if self._is_terminal_run_status(status):
            return False
        await self._cancel_run(base_url, run_id, thread_id)
        return True

    async def _poll_exact_queue_position(
        self,
        *,
        session: aiohttp.ClientSession,
        base_url: str,
        run_id: str,
    ) -> Optional[int]:
        thread_ids = await self._list_busy_thread_ids(session, base_url)
        if not thread_ids:
            return None

        pending_lookup_tasks = [
            self._list_pending_runs_for_thread(session, base_url, thread_id)
            for thread_id in thread_ids
        ]
        results = await asyncio.gather(*pending_lookup_tasks, return_exceptions=True)

        pending_runs: list[dict[str, str]] = []
        for result in results:
            if isinstance(result, list):
                pending_runs.extend(result)
        if not pending_runs:
            return None

        pending_runs.sort(
            key=lambda item: (item.get("created_at", ""), item.get("run_id", ""))
        )
        for idx, item in enumerate(pending_runs, start=1):
            if item.get("run_id") == run_id:
                return idx
        return None

    async def _list_busy_thread_ids(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
    ) -> list[str]:
        thread_ids: list[str] = []
        limit = max(1, int(self.valves.QUEUE_THREAD_SCAN_LIMIT))
        offset = 0
        page_size = min(100, limit)

        while len(thread_ids) < limit:
            payload = {
                "status": "busy",
                "limit": min(page_size, limit - len(thread_ids)),
                "offset": offset,
                "select": ["thread_id"],
            }
            try:
                async with session.post(
                    f"{base_url}/threads/search",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json(content_type=None)
                    if not isinstance(data, list):
                        return []
            except Exception:
                return []

            if not data:
                break

            for thread in data:
                if not isinstance(thread, dict):
                    continue
                thread_id = thread.get("thread_id")
                if thread_id:
                    thread_ids.append(str(thread_id))

            if len(data) < payload["limit"]:
                break
            offset += payload["limit"]

        # Keep insertion order while removing duplicates.
        return list(dict.fromkeys(thread_ids))

    async def _list_pending_runs_for_thread(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        thread_id: str,
    ) -> list[dict[str, str]]:
        pending_runs: list[dict[str, str]] = []
        offset = 0
        limit = 100

        while True:
            try:
                async with session.get(
                    f"{base_url}/threads/{thread_id}/runs",
                    params={"status": "pending", "limit": limit, "offset": offset},
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status != 200:
                        break
                    data = await resp.json(content_type=None)
                    if not isinstance(data, list):
                        break
            except Exception:
                break

            if not data:
                break

            for run in data:
                if not isinstance(run, dict):
                    continue
                pending_run_id = run.get("run_id")
                if not pending_run_id:
                    continue
                status = str(run.get("status") or "").lower()
                if status and status != "pending":
                    continue
                pending_runs.append(
                    {
                        "run_id": str(pending_run_id),
                        "created_at": str(run.get("created_at") or ""),
                    }
                )

            if len(data) < limit:
                break
            offset += limit

        return pending_runs

    async def _create_thread(self, base_url: str) -> Optional[str]:
        payload: dict = {}
        ttl_minutes = int(self.valves.THREAD_TTL_MINUTES)
        if ttl_minutes > 0:
            payload["ttl"] = {"ttl": ttl_minutes, "strategy": "delete"}
        payload["metadata"] = {"source": "openwebui_deep_research_tool"}

        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(f"{base_url}/threads", json=payload) as resp:
                    if resp.status >= 300:
                        return None
                    data = await resp.json(content_type=None)
                    if not isinstance(data, dict):
                        return None
                    thread_id = data.get("thread_id") or data.get("id")
                    return str(thread_id) if thread_id else None
        except Exception:
            return None

    async def _cancel_run(
        self, base_url: str, run_id: Optional[str], thread_id: Optional[str]
    ):
        if not run_id:
            return
        timeout = aiohttp.ClientTimeout(total=15)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                if thread_id:
                    await session.post(
                        f"{base_url}/threads/{thread_id}/runs/{run_id}/cancel",
                        params={"wait": 0, "action": "interrupt"},
                    )
                else:
                    await session.post(
                        f"{base_url}/runs/cancel",
                        json={"run_ids": [run_id]},
                        params={"action": "interrupt"},
                    )
        except Exception:
            pass

    async def _join_for_final_report(
        self,
        *,
        session: aiohttp.ClientSession,
        base_url: str,
        run_id: str,
        thread_id: Optional[str],
        attempts: int,
        delay_seconds: int,
    ) -> str:
        if thread_id:
            join_url = f"{base_url}/threads/{thread_id}/runs/{run_id}/join"
        else:
            join_url = f"{base_url}/runs/{run_id}"

        for attempt in range(attempts):
            try:
                async with session.get(
                    join_url,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        report = self._extract_final_report(data)
                        if report:
                            return report
            except Exception:
                pass

            if attempt < attempts - 1:
                await asyncio.sleep(delay_seconds)

        return ""

    def _extract_final_report(self, payload) -> str:
        if isinstance(payload, dict):
            direct_report = payload.get("final_report")
            if isinstance(direct_report, str) and direct_report.strip():
                return direct_report

            messages = payload.get("messages")
            if isinstance(messages, list):
                for msg in reversed(messages):
                    if isinstance(msg, dict):
                        role = str(msg.get("type") or msg.get("role") or "").lower()
                        if role and role not in {"ai", "assistant"}:
                            continue
                        content = msg.get("content")
                        if isinstance(content, str) and content.strip():
                            return content

            for key in ("values", "state", "output", "result", "data"):
                if key in payload:
                    nested_report = self._extract_final_report(payload.get(key))
                    if nested_report:
                        return nested_report

            for value in payload.values():
                nested_report = self._extract_final_report(value)
                if nested_report:
                    return nested_report

        elif isinstance(payload, list):
            for item in payload:
                nested_report = self._extract_final_report(item)
                if nested_report:
                    return nested_report

        return ""

    def _extract_embedded_selection(
        self, query: str
    ) -> tuple[Optional[int], Optional[str], Optional[str]]:
        if not query:
            return None, None, None
        pattern = re.compile(
            r"^run\s+deep\s+research\s+level\s+(?P<level>\d+)\s+output\s+(?P<output>.+?)\s+on:\s*(?P<query>.+)$",
            re.IGNORECASE | re.DOTALL,
        )
        match = pattern.match(query.strip())
        if not match:
            return None, None, None
        try:
            level_val = int(match.group("level").strip())
        except ValueError:
            level_val = None

        raw_output = match.group("output").strip()
        if raw_output.lower().startswith("custom:"):
            output_type = raw_output  # Pass through as-is
        else:
            output_type = self._normalize_output_type(raw_output)

        return (
            level_val,
            output_type,
            match.group("query"),
        )

    def _extract_urls(self, text: str) -> list[str]:
        if not text:
            return []
        urls: list[str] = []
        for raw_url in URL_PATTERN.findall(text):
            cleaned = self._normalize_url(raw_url)
            if cleaned:
                urls.append(cleaned)
        return urls

    def _normalize_url(self, url: str) -> str:
        raw = str(url or "").strip().rstrip(".,;:)")
        if not raw:
            return ""
        try:
            parsed = urlparse(raw)
        except Exception:
            return ""
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""
        path = parsed.path or ""
        normalized = parsed._replace(
            scheme=parsed.scheme.lower(),
            netloc=parsed.netloc.lower(),
            query="",
            fragment="",
            path=path.rstrip("/") if path and path != "/" else path,
        )
        return urlunparse(normalized)

    def _domain_for_url(self, url: str) -> str:
        try:
            host = (urlparse(url).netloc or "").lower()
        except Exception:
            return ""
        if host.startswith("www."):
            host = host[4:]
        return host

    def _is_low_trust_domain(self, domain: str) -> bool:
        if not domain:
            return False
        return any(domain == d or domain.endswith(f".{d}") for d in LOW_TRUST_DOMAINS)

    def _is_primary_domain(self, domain: str) -> bool:
        if not domain:
            return False
        if domain.endswith(".gov") or domain.endswith(".edu"):
            return True
        return any(domain == d or domain.endswith(f".{d}") for d in PRIMARY_SOURCE_HINTS)

    def _extract_sources_section_urls(self, text: str) -> list[str]:
        if not text:
            return []
        section_match = re.search(
            r"^#{2,3}\s*Sources\b(?P<section>.*?)(?:^#{1,3}\s+|\Z)",
            text,
            flags=re.IGNORECASE | re.DOTALL | re.MULTILINE,
        )
        if not section_match:
            return []
        return self._extract_urls(section_match.group("section"))

    def _normalize_sources_section_markdown(
        self,
        report: str,
        fallback_urls: list[str],
    ) -> str:
        if not report:
            return ""

        fallback = []
        seen_fallback: set[str] = set()
        for url in fallback_urls:
            normalized = self._normalize_url(url)
            if normalized and normalized not in seen_fallback:
                seen_fallback.add(normalized)
                fallback.append(normalized)

        heading_match = re.search(
            r"^#{2,3}\s*Sources\b[^\n]*",
            report,
            flags=re.IGNORECASE | re.MULTILINE,
        )

        if not heading_match:
            if not fallback:
                return report
            block = "\n".join(f"[{i}] {url}" for i, url in enumerate(fallback, 1))
            return report.rstrip() + "\n\n## Sources\n" + block

        heading_start = heading_match.start()
        heading_end = heading_match.end()

        tail = report[heading_end:]
        next_heading = re.search(r"^#{1,3}\s+\S", tail, flags=re.MULTILINE)
        section_end = heading_end + next_heading.start() if next_heading else len(report)

        section_body = report[heading_end:section_end]
        section_urls = self._extract_urls(section_body)

        normalized_urls: list[str] = []
        seen_urls: set[str] = set()
        for raw_url in (section_urls or fallback):
            normalized = self._normalize_url(raw_url)
            if not normalized or normalized in seen_urls:
                continue
            seen_urls.add(normalized)
            normalized_urls.append(normalized)

        if not normalized_urls:
            return report

        header_line = report[heading_start:heading_end].strip()
        normalized_section = "\n".join(
            f"[{i}] {url}" for i, url in enumerate(normalized_urls, 1)
        )

        prefix = report[:heading_start].rstrip()
        suffix = report[section_end:].lstrip("\n")

        rebuilt = prefix + "\n\n" + header_line + "\n" + normalized_section
        if suffix:
            rebuilt += "\n\n" + suffix
        return rebuilt

    def _extract_evidence_ledger_urls_from_report(self, text: str) -> list[str]:
        if not text:
            return []
        candidates: list[str] = []
        marker = re.search(
            r"###\s*Evidence Ledger \(JSON\)\s*(?P<body>.*?)(?:^#{1,3}\s+|\Z)",
            text,
            flags=re.IGNORECASE | re.DOTALL | re.MULTILINE,
        )
        if marker:
            candidates.extend(
                re.findall(r"```json\s*(.*?)\s*```", marker.group("body"), flags=re.DOTALL | re.IGNORECASE)
            )
            candidates.append(marker.group("body"))

        urls: list[str] = []
        for candidate in candidates:
            try:
                data = json.loads(candidate)
            except Exception:
                continue
            if isinstance(data, dict):
                data = data.get("evidence_ledger")
            if not isinstance(data, list):
                continue
            for item in data:
                if not isinstance(item, dict):
                    continue
                normalized_url = self._normalize_url(str(item.get("source_url", "")))
                if normalized_url:
                    urls.append(normalized_url)
        return urls

    def _extract_evidence_ledger_from_payload(self, payload: Any) -> list[dict[str, str]]:
        extracted: list[dict[str, str]] = []

        if isinstance(payload, dict):
            evidence_items = payload.get("evidence_ledger")
            if isinstance(evidence_items, list):
                extracted = self._merge_evidence_items(extracted, evidence_items)

            for value in payload.values():
                extracted = self._merge_evidence_items(
                    extracted,
                    self._extract_evidence_ledger_from_payload(value),
                )

        elif isinstance(payload, list):
            for item in payload:
                extracted = self._merge_evidence_items(
                    extracted,
                    self._extract_evidence_ledger_from_payload(item),
                )

        return extracted

    def _merge_evidence_items(
        self,
        existing: list[dict[str, str]],
        incoming: Any,
    ) -> list[dict[str, str]]:
        merged = list(existing)
        if not isinstance(incoming, list):
            return merged

        seen = {
            (
                str(item.get("claim", "")).strip().lower(),
                self._normalize_url(str(item.get("source_url", ""))),
            )
            for item in merged
            if isinstance(item, dict)
        }

        for item in incoming:
            if not isinstance(item, dict):
                continue
            claim = str(item.get("claim", "")).strip()
            source_url = self._normalize_url(str(item.get("source_url", "")))
            if not claim or not source_url:
                continue
            key = (claim.lower(), source_url)
            if key in seen:
                continue
            seen.add(key)
            merged.append(
                {
                    "claim": claim,
                    "entity": str(item.get("entity", "")).strip(),
                    "date": str(item.get("date", "")).strip(),
                    "metric": str(item.get("metric", "")).strip(),
                    "source_url": source_url,
                    "dimension": str(item.get("dimension", "")).strip(),
                }
            )

        return merged

    def _curate_sources(
        self,
        final_report: str,
        evidence_ledger: list[dict[str, str]],
        *,
        max_sources: int,
        strict_mode: bool,
        min_primary_ratio: float,
        allow_low_trust_fallback: bool,
    ) -> tuple[list[str], dict[str, Any]]:
        source_candidates: dict[str, dict[str, Any]] = {}

        def add_candidate(url: str, origin: str):
            normalized = self._normalize_url(url)
            if not normalized:
                return
            domain = self._domain_for_url(normalized)
            if not domain:
                return

            entry = source_candidates.setdefault(
                normalized,
                {
                    "url": normalized,
                    "domain": domain,
                    "origins": set(),
                    "score": 0,
                    "is_primary": False,
                    "is_low_trust": False,
                },
            )
            entry["origins"].add(origin)

        for item in evidence_ledger:
            if isinstance(item, dict):
                add_candidate(str(item.get("source_url", "")), "evidence")

        for url in self._extract_evidence_ledger_urls_from_report(final_report):
            add_candidate(url, "evidence")

        for url in self._extract_sources_section_urls(final_report):
            add_candidate(url, "sources_section")

        if not source_candidates:
            fallback_urls = self._extract_urls(final_report)
            for url in fallback_urls:
                add_candidate(url, "fallback")

        for entry in source_candidates.values():
            domain = entry["domain"]
            is_primary = self._is_primary_domain(domain)
            is_low_trust = self._is_low_trust_domain(domain)
            score = 0
            if "evidence" in entry["origins"]:
                score += 4
            if "sources_section" in entry["origins"]:
                score += 2
            if "fallback" in entry["origins"]:
                score += 1
            if is_primary:
                score += 4
            if is_low_trust:
                score -= 5

            entry["is_primary"] = is_primary
            entry["is_low_trust"] = is_low_trust
            entry["score"] = score

        ranked = sorted(
            source_candidates.values(),
            key=lambda item: (
                int(item["is_primary"]),
                int("evidence" in item["origins"]),
                int("sources_section" in item["origins"]),
                item["score"],
            ),
            reverse=True,
        )

        if strict_mode:
            strict_ranked = [item for item in ranked if item["score"] >= 0 and not item["is_low_trust"]]
            if strict_ranked:
                ranked = strict_ranked

        if not ranked and source_candidates:
            ranked = sorted(source_candidates.values(), key=lambda item: item["score"], reverse=True)

        selected = ranked[:max_sources]
        primary_count = sum(1 for item in selected if item["is_primary"])
        low_trust_count = sum(1 for item in selected if item["is_low_trust"])

        if strict_mode and selected:
            target_primary = int(len(selected) * min_primary_ratio)
            if primary_count < target_primary:
                primaries = [item for item in ranked if item["is_primary"]]
                non_primaries = [item for item in selected if not item["is_primary"]]
                replacement_pool = [
                    item for item in primaries if item["url"] not in {s["url"] for s in selected}
                ]
                while replacement_pool and non_primaries and primary_count < target_primary:
                    selected.remove(non_primaries.pop())
                    selected.append(replacement_pool.pop(0))
                    primary_count = sum(1 for item in selected if item["is_primary"])

        if strict_mode and not allow_low_trust_fallback:
            selected = [item for item in selected if not item["is_low_trust"]]

        selected = selected[:max_sources]
        primary_count = sum(1 for item in selected if item["is_primary"])
        low_trust_count = sum(1 for item in selected if item["is_low_trust"])
        selected_urls = [item["url"] for item in selected]
        primary_ratio = (primary_count / len(selected_urls)) if selected_urls else 0.0

        warnings: list[str] = []
        if selected_urls and primary_ratio < min_primary_ratio:
            warnings.append(
                "Primary-source ratio below configured threshold; limited high-quality primary sources were available."
            )
        if low_trust_count > 0:
            warnings.append(
                "Low-trust domains retained only where alternatives were limited."
            )

        quality = {
            "strict_mode": strict_mode,
            "max_sources": max_sources,
            "candidate_count": len(source_candidates),
            "selected_count": len(selected_urls),
            "primary_count": primary_count,
            "primary_ratio": round(primary_ratio, 3),
            "low_trust_count": low_trust_count,
            "warnings": warnings,
        }
        return selected_urls, quality

    # ─────────────────────────────────────────
    # Emitters
    # ─────────────────────────────────────────
    async def _emit_status(
        self,
        emitter: Optional[Callable[[dict], Awaitable[None]]],
        description: str,
        done: bool = False,
    ):
        if not emitter:
            return
        try:
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
        except Exception:
            pass

    async def _emit_citation(
        self,
        emitter: Optional[Callable[[dict], Awaitable[None]]],
        url: str,
        title: str = "",
    ):
        if not emitter or not url:
            return
        display = title or url
        try:
            await emitter(
                {
                    "type": "source",
                    "data": {
                        "document": [display],
                        "metadata": [{"source": url, "name": display}],
                        "source": {"name": display, "url": url},
                    },
                }
            )
        except Exception:
            pass

    # ─────────────────────────────────────────
    # Result packaging
    # ─────────────────────────────────────────
    def _build_result_package(
        self,
        *,
        query: str,
        level_key: str,
        output_key: str,
        elapsed: float,
        visited_urls: list,
        final_report: str,
        source_quality: Optional[dict[str, Any]] = None,
    ) -> str:
        if output_key.startswith("custom:"):
            custom_desc = output_key[7:].strip()
            output_info = {
                "key": "custom",
                "label": custom_desc,
                "emoji": "✏️",
                "custom_description": custom_desc,
            }
        else:
            output_info = {
                "key": output_key,
                "label": OUTPUT_TYPES[output_key]["label"],
                "emoji": OUTPUT_TYPES[output_key]["emoji"],
            }

        package = {
            "query": query,
            "level": {
                "key": level_key,
                "label": RESEARCH_LEVELS[level_key]["label"],
                "emoji": RESEARCH_LEVELS[level_key]["emoji"],
            },
            "output_type": output_info,
            "elapsed_seconds": elapsed,
            "source_count": len(visited_urls),
            "sources": visited_urls,
            "source_quality": source_quality or {},
            "research_report_markdown": final_report.strip(),
        }
        return json.dumps(package, ensure_ascii=False)
