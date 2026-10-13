"""Streamlit Chat Application for Text-to-SQL Guarded Assistant.

Frontend v8: Dark-mode-only UI with pure CSS smooth continuous progress bar 
filling across pipeline cards during active execution.
"""

import html
import re
import threading
import time

import pandas as pd
import streamlit as st

from src.config import (
    DATABASE_PATH,
    GEMINI_API_KEY,
    ALLOWED_TABLES,
    DEFAULT_ROW_LIMIT,
    MAX_ROW_LIMIT,
)
from src.database import (
    get_schema_summary,
    get_table_columns_map,
    get_table_row_counts,
    get_sample_rows,
)
from src.ingestion import populate_default_database
from src.sql_generator import generate_sql_query
from src.sql_validator import validate_and_sanitize_sql
from src.query_executor import execute_read_only_query

st.set_page_config(
    page_title="Guarded SQL Assistant",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --------------------------------------------------------------------------- #
# Theme tokens (Dark-only Palette)
# --------------------------------------------------------------------------- #
DARK = {
    "scheme": "dark",
    "bg-solid": "#131314",
    "hero-glow": "radial-gradient(ellipse 75% 45% at 50% 100%, rgba(52,98,230,0.26), transparent 70%)",
    "sidebar": "#1E1F20",
    "surface": "#1E1F20",
    "surface2": "#282A2C",
    "field": "#282A2C",
    "chip": "#1E1F20",
    "chip-hover": "#2B2D30",
    "bubble": "#282A2C",
    "line": "#34373A",
    "line-strong": "#5E6163",
    "ink": "#E3E3E3",
    "ink-soft": "#C4C7C5",
    "ink-faint": "#9AA0A6",
    "accent": "#A8C7FA",
    "accent-strong": "#3C78E0",
    "accent-wash": "#2B3D5C",
    "accent-ring": "rgba(168,199,250,0.30)",
    "on-accent": "#FFFFFF",
    "on-solid": "#131314",
    "green": "#81C995",
    "red": "#F28B82",
    "amber": "#FDD663",
    "amber-wash": "#392F14",
    "amber-bd": "#6B5A1E",
    "ok-bg": "#16301F",
    "ok-bd": "#2D5A3C",
    "ok-ink": "#A8DAB5",
    "bad-bg": "#3A1F1D",
    "bad-bd": "#6E3430",
    "bad-ink": "#F9B9B3",
    "warn-bg": "#392F14",
    "warn-bd": "#6B5A1E",
    "warn-ink": "#FDE293",
    "shadow": "0 1px 3px rgba(0,0,0,0.45)",
    "shadow-input": "0 2px 14px rgba(0,0,0,0.40)",
    "code-bg": "#18191B",
    "code-head": "#232527",
    "code-line": "#34373A",
    "s-kw": "#8AB4F8",
    "s-fn": "#D7AEFB",
    "s-str": "#81C995",
    "s-num": "#FDD663",
    "s-id": "#E3E3E3",
    "s-cm": "#9AA0A6",
}

BASE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  --font: 'Google Sans','Google Sans Text','DM Sans',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
  --mono: 'JetBrains Mono','Google Sans Code',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  --grad: linear-gradient(135deg,#4285F4 0%,#9B72CB 55%,#D96570 100%);
  color-scheme: var(--scheme);
}

/* ---------- Base canvas ---------- */
.stApp { background-color: var(--bg-solid) !important; color: var(--ink); font-family: var(--font) !important; }
[data-testid="stAppViewContainer"], [data-testid="stMain"], section.main { background: transparent !important; }
.stApp [data-testid="stMarkdownContainer"], .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp p, .stApp li,
.stApp label, .stApp summary, .stApp button, .stApp input, .stApp textarea, .stApp td, .stApp th { font-family: var(--font) !important; }
header[data-testid="stHeader"] { background: transparent !important; }
header[data-testid="stHeader"] button, [data-testid="stSidebarCollapseButton"] button,
[data-testid="stExpandSidebarButton"], [data-testid="stSidebarCollapsedControl"] button { color: var(--ink-soft) !important; }
[data-testid="stAppDeployButton"], .stDeployButton, #MainMenu, [data-testid="stMainMenu"], [data-testid="stDecoration"], footer { display: none !important; }

[data-testid="stMainBlockContainer"], [data-testid="stAppViewBlockContainer"], [data-testid="block-container"] {
  max-width: 880px !important; margin: 0 auto; padding: 3.2rem 1.5rem 9rem !important;
}
[data-testid="stBottomBlockContainer"] { max-width: 880px !important; margin: 0 auto; padding: .25rem 1.5rem 1.4rem !important; }
[data-testid="stBottom"], [data-testid="stBottom"] > div { background: transparent !important; }
[data-testid="stBottom"] > div { background: linear-gradient(to top, var(--bg-solid) 60%, transparent) !important; }

/* ---------- Text colour safety net ---------- */
[data-testid="stMarkdownContainer"] { color: var(--ink); }
[data-testid="stMarkdownContainer"] p:not([class]), [data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] strong, [data-testid="stWidgetLabel"] *,
[data-testid="stExpander"] summary *, [data-testid="stSidebar"] label * { color: var(--ink) !important; }
[data-testid="stCaptionContainer"] * { color: var(--ink-soft) !important; }

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"], [data-testid="stSidebarContent"] { background: var(--sidebar) !important; border-right: none !important; }
[data-testid="stSidebarContent"] { padding: 1rem .75rem 1.5rem; }
[data-testid="stSidebarHeader"] { background: transparent !important; }
.brand { display:flex; align-items:center; gap:10px; padding:.25rem .5rem .9rem; }
.logo { width:30px; height:30px; display:grid; place-items:center; font-size:1.35rem; line-height:1;
  background: var(--grad); -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; color:transparent; }
.brand-name { font-weight:500; font-size:1.18rem; color: var(--ink); letter-spacing:-.01em; }
.side-heading { font-weight:500; font-size:.78rem; color: var(--ink-soft); margin: 1.3rem 0 .45rem .6rem; letter-spacing:.01em; }
.table-row { display:flex; align-items:center; justify-content:space-between; gap:8px; padding:7px 12px; border-radius:12px; transition: background .15s ease; }
.table-row:hover { background: var(--chip-hover); }
.table-row .tn { font-family: var(--mono); font-size:.8rem; color: var(--ink); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.table-row .tc { font-size:.74rem; color: var(--ink-soft); background: var(--field); padding: 2px 9px; border-radius: 999px; white-space:nowrap; }

[data-testid="stSidebar"] div.stButton > button { background: transparent; border: none; box-shadow:none; border-radius: 999px;
  min-height: 2.35rem; padding: .35rem .85rem; color: var(--ink) !important; font-weight:400; font-size:.88rem; transform:none; }
[data-testid="stSidebar"] div.stButton > button:hover { background: var(--chip-hover); color: var(--ink) !important; transform:none; border:none; }
[data-testid="stSidebar"] div.stButton > button p { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:.88rem; }
[class*="st-key-new_chat"] button { background: var(--bubble) !important; font-weight:500 !important; margin-bottom:.25rem; }
[class*="st-key-new_chat"] button:hover { background: var(--chip-hover) !important; }

/* ---------- Top bar ---------- */
.topbar { display:flex; align-items:center; gap:12px; min-height:2.4rem; }
.topbar-title { font-size:1.05rem; font-weight:500; color: var(--ink); letter-spacing:-.005em; }
.model-pill { font-size:.76rem; color: var(--ink-soft); background: var(--chip); padding: 4px 12px; border-radius:999px; font-family: var(--mono); }

/* ---------- Hero (empty state) ---------- */
.hero { text-align:center; padding: 8vh 0 1.4rem; }
.hero-spark { font-size:2.3rem; line-height:1; margin-bottom:.9rem; display:inline-block;
  background: var(--grad); -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; color:transparent; }
.hero-title { font-weight:400; font-size:clamp(1.8rem,4.2vw,2.6rem); letter-spacing:-.02em; line-height:1.15; margin:0; padding:0; color: var(--ink); }
.hero-sub { font-size:1rem; color: var(--ink-soft); margin:.75rem auto 0; max-width:52ch; line-height:1.55; }
.section-title { font-weight:500; font-size:.82rem; color: var(--ink-soft); margin: 1.6rem 0 .5rem .25rem; letter-spacing:.01em; }

[data-testid="stMain"] div.stButton > button, section.main div.stButton > button {
  width:100%; border-radius:18px; border:1px solid transparent; background: var(--chip); color: var(--ink) !important;
  font-weight:400; font-size:.9rem; line-height:1.4; padding:.75rem 1rem; min-height:3.1rem; box-shadow:none; transition: background .15s ease; }
[data-testid="stMain"] div.stButton > button > div, section.main div.stButton > button > div { justify-content:flex-start; text-align:left; width:100%; }
[data-testid="stMain"] div.stButton > button p, section.main div.stButton > button p { color: inherit !important; font-size:.9rem; }
[data-testid="stMain"] div.stButton > button:hover, section.main div.stButton > button:hover { background: var(--chip-hover); border-color: transparent; color: var(--ink) !important; }
div.stButton > button:focus-visible, div.stDownloadButton > button:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
[class*="st-key-hero_sec"] button { box-shadow: inset 3px 0 0 var(--red) !important; font-family: var(--mono) !important; font-size:.82rem !important; }

button[kind="primary"], [data-testid="stBaseButton-primary"] { background: var(--red) !important; color: var(--on-solid) !important; border:1px solid var(--red) !important;
  border-radius: 999px !important; padding: .45rem 1.1rem !important; min-height:2.5rem !important; }
button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover { filter: brightness(1.08); background: var(--red) !important; }
button[kind="primary"] p, [data-testid="stBaseButton-primary"] p { color: var(--on-solid) !important; font-weight:600 !important; }

div.stDownloadButton > button { border-radius:999px; background: transparent; color: var(--accent) !important; border:1px solid var(--line-strong); font-weight:500; padding:.45rem 1.1rem; }
div.stDownloadButton > button p { color: var(--accent) !important; }
div.stDownloadButton > button:hover { background: var(--accent-wash); border-color: var(--accent); }

/* ---------- Pipeline strip with Smooth Pure CSS Progress Filling ---------- */
.pipe { display:flex; flex-wrap:wrap; gap:8px; margin:.2rem 0 1.2rem; }
.pipe-step { 
  position: relative; 
  display:flex; 
  align-items:center; 
  gap:10px; 
  padding:6px 16px 6px 7px; 
  border-radius:999px; 
  background: var(--chip); 
  overflow: hidden;
  border: 1px solid var(--line);
}
.pipe-step::before {
  content: "";
  position: absolute;
  top: 0; left: 0; bottom: 0;
  width: 0%;
  background: var(--accent-wash);
  z-index: 0;
}
.pipe-step > * { position: relative; z-index: 1; }

.pipe-num { width:24px; height:24px; border-radius:50%; border:1.5px solid var(--line-strong); color: var(--ink-soft); display:grid; place-items:center; font-size:.74rem; font-weight:600; flex:none; }
.pipe-name { font-weight:500; font-size:.83rem; color: var(--ink); line-height:1.2; }
.pipe-state { font-size:.72rem; color: var(--ink-soft); line-height:1.2; }

.pipe-step.ok { border-color: var(--green); }
.pipe-step.ok::before { width: 100% !important; background: var(--ok-bg); }
.pipe-step.ok .pipe-num { background: var(--green); border-color: var(--green); color: var(--on-solid); }
.pipe-step.ok .pipe-state { color: var(--green); font-weight:600; }

.pipe-step.fail { border-color: var(--red); }
.pipe-step.fail::before { width: 100% !important; background: var(--bad-bg); }
.pipe-step.fail .pipe-num { background: var(--red); border-color: var(--red); color: var(--on-solid); }
.pipe-step.fail .pipe-state { color: var(--red); font-weight:600; }

.pipe-step.skip { opacity:.55; }

/* Continuous smooth sweeping progress animation across stages during run */
.pipe-step.run { border-color: var(--accent); }
.pipe-step.run::before { 
  animation: smoothSweep 1.8s infinite cubic-bezier(0.4, 0, 0.2, 1); 
}
.pipe-step.run .pipe-num { border-color: var(--accent); color: var(--accent); animation: pulse 1.4s ease-in-out infinite; }
.pipe-step.run .pipe-state { color: var(--accent); font-weight:600; }

@keyframes smoothSweep {
  0% { width: 0%; opacity: 0.2; }
  50% { width: 100%; opacity: 0.5; }
  100% { width: 0%; opacity: 0.2; }
}
@keyframes pulse { 0%,100% { box-shadow: 0 0 0 0 var(--accent-ring); } 50% { box-shadow: 0 0 0 6px transparent; } }

/* ---------- Chat ---------- */
[data-testid="stChatMessage"] { background: transparent !important; border: none !important; box-shadow:none !important; padding: .5rem 0 !important; margin-bottom:.35rem; gap:.9rem; }
[data-testid="stChatMessageAvatarUser"] { display:none !important; }
[data-testid="stChatMessageAvatarAssistant"] { width:2rem; height:2rem; font-size:1.45rem; line-height:1; align-self:flex-start;
  background-color: transparent !important; background-image: var(--grad) !important; -webkit-background-clip:text !important; background-clip:text !important;
  -webkit-text-fill-color:transparent; color:transparent !important; }
[data-testid="stChatMessageContent"] { min-width:0; }
[data-testid="stChatMessage"]:has(.user-q) { justify-content:flex-end; }
[data-testid="stChatMessage"]:has(.user-q) [data-testid="stChatMessageContent"] { flex: 0 1 auto; max-width: 82%; }
.user-q { display:inline-block; background: var(--bubble); color: var(--ink); font-size:1rem; line-height:1.5; font-weight:400;
  padding:.7rem 1.15rem; border-radius: 22px 22px 6px 22px; word-break: break-word; }

/* Prompt box */
[data-testid="stChatInput"] { max-width: 880px; margin: 0 auto; }
[data-testid="stChatInput"] > div { background: var(--chip) !important; border:1px solid transparent !important; border-radius: 28px !important; box-shadow: var(--shadow-input); min-height:3.5rem; align-items:center; }
[data-testid="stChatInput"] > div [data-baseweb] { background: transparent !important; border:none !important; box-shadow:none !important; }
[data-testid="stChatInput"] textarea { color: var(--ink) !important; background: transparent !important; font-size: 1rem; padding-left:.5rem; }
[data-testid="stChatInput"] textarea::placeholder { color: var(--ink-faint) !important; -webkit-text-fill-color: var(--ink-faint) !important; opacity:1; }
[data-testid="stChatInput"]:focus-within > div { border-color: var(--line-strong) !important; }
[data-testid="stChatInputSubmitButton"] { background: var(--accent-strong) !important; color: var(--on-accent) !important; border-radius:50% !important; }
[data-testid="stChatInputSubmitButton"]:disabled { background: transparent !important; color: var(--ink-faint) !important; }

/* ---------- Live execution row ---------- */
.live { display:flex; align-items:center; gap:14px; padding:.6rem 0; }
.spin { width:22px; height:22px; border-radius:50%; border:3px solid var(--accent-wash); border-top-color: var(--accent); animation: spin .8s linear infinite; flex:none; }
@keyframes spin { to { transform: rotate(360deg); } }
.live-title { font-weight:500; color: var(--ink); font-size:.98rem; }
.live-sub { font-size:.82rem; color: var(--ink-soft); }

/* ---------- Verdicts & chips ---------- */
.verdict { display:flex; gap:12px; align-items:flex-start; border-radius:16px; padding:12px 16px; margin:.7rem 0; border:1px solid; }
.verdict .mark { flex:none; width:22px; height:22px; border-radius:50%; display:grid; place-items:center; font-size:.72rem; font-weight:700; margin-top:1px; }
.verdict b { display:block; font-size:.92rem; font-weight:600; margin-bottom:2px; }
.verdict span { font-size:.85rem; line-height:1.5; }
.verdict.ok { background: var(--ok-bg); border-color: var(--ok-bd); color: var(--ok-ink); }
.verdict.ok .mark { background: var(--green); color: var(--on-solid); }
.verdict.bad { background: var(--bad-bg); border-color: var(--bad-bd); color: var(--bad-ink); }
.verdict.bad .mark { background: var(--red); color: var(--on-solid); }
.verdict.warn { background: var(--warn-bg); border-color: var(--warn-bd); color: var(--warn-ink); }
.verdict.warn .mark { background: var(--amber); color: var(--on-solid); }
.chips { display:flex; flex-wrap:wrap; gap:8px; margin:.9rem 0 .6rem; }
.chip { padding:4px 13px; border-radius:999px; font-size:.78rem; font-weight:500; background: var(--chip); color: var(--ink-soft); }
.chip b { color: var(--ink); font-weight:600; }
.chip.warn { background: var(--amber-wash); color: var(--amber); border:1px solid var(--amber-bd); }
.panel-title { font-weight:500; font-size:.8rem; color: var(--ink-soft); margin:1rem 0 .3rem .2rem; }

/* ---------- SQL code cards ---------- */
.codecard { border-radius:16px; background: var(--code-bg); border:1px solid var(--code-line); overflow:hidden; margin:.3rem 0 .9rem; }
.codehead { display:flex; align-items:center; justify-content:space-between; padding:7px 16px; background: var(--code-head); color: var(--ink-soft); font-size:.74rem; font-weight:500; letter-spacing:.02em; }
.codehead .lang { font-family: var(--mono); }
pre.sql { background: transparent !important; color: var(--s-id) !important; margin:0 !important; padding:14px 18px 16px !important; border:none !important; border-radius:0 !important;
  font-family: var(--mono) !important; font-size:.85rem; line-height:1.75; overflow-x:auto; white-space:pre; tab-size:4; }
pre.sql.wrap { white-space: pre-wrap; word-break: break-word; font-size:.78rem; line-height:1.65; }
pre.sql span { font-family: var(--mono) !important; }
.t-kw { color: var(--s-kw); font-weight:500; } .t-fn { color: var(--s-fn); } .t-str { color: var(--s-str); }
.t-num { color: var(--s-num); } .t-id { color: var(--s-id); } .t-comment { color: var(--s-cm); font-style:italic; }
[data-testid="stCode"], [data-testid="stCode"] pre { background: var(--code-bg) !important; border-radius:12px !important; }
[data-testid="stCode"] pre, [data-testid="stCode"] code, [data-testid="stCode"] code span { color: var(--ink) !important; font-family: var(--mono) !important; font-size:.84rem !important; }

/* ---------- Tables ---------- */
.tbl-wrap { max-height:420px; overflow:auto; border:1px solid var(--line); border-radius:16px; background: var(--surface); margin: .5rem 0; }
.tbl { border-collapse:collapse; width:100%; font-size:.86rem; margin:0; }
.tbl th, .tbl td { border-left:0 !important; border-right:0 !important; border-top:0 !important; }
.tbl th { position:sticky; top:0; background: var(--surface2); color: var(--ink); text-align:left; padding:11px 16px; font-weight:600; font-size:.78rem; white-space:nowrap; border-bottom:1px solid var(--line) !important; z-index:2; }
.tbl td { padding:10px 16px; color: var(--ink); border-bottom:1px solid var(--line) !important; white-space:nowrap; background: transparent; }
.tbl tbody tr:last-child td { border-bottom:none !important; }
.tbl tbody tr:hover td { background: var(--surface2); }
.tbl .num, .tbl th.num { text-align:right; font-variant-numeric: tabular-nums; }
.tbl .null { color: var(--ink-faint); }
.tbl-note { font-size:.8rem; color: var(--ink-soft); margin-top:.35rem; }

/* ---------- Bar chart ---------- */
.bars { background: var(--surface); border:1px solid var(--line); border-radius:16px; padding:16px 20px; margin:.5rem 0; }
.bars-title { font-weight:500; font-size:.8rem; color: var(--ink-soft); margin-bottom:12px; }
.bar-row { display:grid; grid-template-columns: minmax(110px, 28%) 1fr auto; gap:14px; align-items:center; margin:9px 0; }
.bar-label { font-size:.86rem; color: var(--ink); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.bar-track { height:10px; background: var(--surface2); border-radius:999px; overflow:hidden; }
.bar-fill { height:100%; border-radius:999px; background: var(--accent-strong); }
.bar-val { font-size:.84rem; color: var(--ink); font-variant-numeric: tabular-nums; font-weight:600; }

/* ---------- Widgets ---------- */
[data-testid="stExpander"] { background: transparent; border:1px solid var(--line); border-radius:16px; box-shadow:none; overflow:hidden; }
[data-testid="stExpander"] details, [data-testid="stExpander"] summary { background: transparent !important; }
[data-testid="stExpander"] summary:hover { background: var(--chip-hover) !important; }
[data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="base-input"] { background: var(--field) !important; border-color: var(--line) !important; border-radius: 12px !important; }
[data-baseweb="input"] input, [data-baseweb="select"] * { color: var(--ink) !important; -webkit-text-fill-color: var(--ink) !important; }
[data-baseweb="popover"] *, [data-baseweb="menu"] { background: var(--surface) !important; color: var(--ink) !important; }
[data-baseweb="menu"] li:hover { background: var(--accent-wash) !important; }
[data-testid="stAlert"] { background: var(--surface2) !important; border-radius:16px; border: 1px solid var(--line); }
[data-testid="stAlert"] * { color: var(--ink) !important; }
.stTabs [data-baseweb="tab"] { background: transparent !important; }
.stTabs [data-baseweb="tab"] p { color: var(--ink-soft) !important; font-weight:500; }
.stTabs [aria-selected="true"] p { color: var(--accent) !important; }
.stTabs [data-baseweb="tab-highlight"] { background: var(--accent) !important; height: 3px; border-radius: 3px; }
.stTabs [data-baseweb="tab-border"] { background: var(--line) !important; }

@media (max-width: 760px) {
  [data-testid="stMainBlockContainer"], [data-testid="stAppViewBlockContainer"], [data-testid="block-container"] { padding: 3rem 1rem 8rem !important; }
  .hero { padding-top: 4vh; }
  [data-testid="stChatMessage"]:has(.user-q) [data-testid="stChatMessageContent"] { max-width: 92%; }
}
@media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }
"""

HERO_CSS = """
.stApp { background-image: var(--hero-glow) !important; background-attachment: fixed !important; }
"""

def build_css(hero: bool = False) -> str:
    tokens = DARK
    root = ":root{" + "".join(f"--{k}:{v};" for k, v in tokens.items()) + "}"
    return f"<style>{root}{BASE_CSS}{HERO_CSS if hero else ''}</style>"

st.markdown(build_css(hero=not st.session_state.get("messages")), unsafe_allow_html=True)

# --------------------------------------------------------------------------- #
# Content constants
# --------------------------------------------------------------------------- #
EXAMPLE_QUESTIONS = [
    "How many orders are there?",
    "Which five products have the highest total sales?",
    "Which customers have placed the most orders?",
    "What is the total quantity ordered by product category?",
    "Which cities have the most customers?",
    "How many orders are pending?",
    "Show the ten most recent orders with customer names.",
]
SECURITY_TESTS = [
    "DROP TABLE customers;",
    "DELETE FROM orders WHERE order_id = 1;",
]
RAW_SQL_PREFIXES = (
    "SELECT", "WITH", "DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "PRAGMA",
)

SQL_KEYWORDS = {
    "SELECT", "FROM", "WHERE", "GROUP", "BY", "ORDER", "LIMIT", "OFFSET", "JOIN", "LEFT", "RIGHT",
    "INNER", "OUTER", "FULL", "CROSS", "ON", "AS", "AND", "OR", "NOT", "IN", "IS", "NULL", "LIKE",
    "BETWEEN", "HAVING", "DISTINCT", "UNION", "ALL", "CASE", "WHEN", "THEN", "ELSE", "END", "ASC",
    "DESC", "WITH", "INSERT", "INTO", "VALUES", "UPDATE", "SET", "DELETE", "DROP", "CREATE", "ALTER",
    "TABLE", "PRAGMA", "EXISTS", "CAST", "OVER", "PARTITION",
}
_TOKEN = re.compile(
    r"(?P<comment>--[^\n]*)|(?P<string>'(?:[^']|'')*')|(?P<qid>\"(?:[^\"]|\"\")*\"|`[^`]*`)"
    r"|(?P<number>\b\d+(?:\.\d+)?\b)|(?P<word>[A-Za-z_][A-Za-z_0-9]*)"
)


# --------------------------------------------------------------------------- #
# SQL pretty-printer
# --------------------------------------------------------------------------- #
_FMT_KEYWORDS = SQL_KEYWORDS | {
    "USING", "NATURAL", "INTERSECT", "EXCEPT", "GLOB", "ESCAPE", "COLLATE", "RECURSIVE", "TRUE", "FALSE",
}
_FUNC_UPPER = {
    "COUNT", "SUM", "AVG", "MIN", "MAX", "ROUND", "COALESCE", "IFNULL", "NULLIF", "LENGTH", "LOWER",
    "UPPER", "TRIM", "SUBSTR", "SUBSTRING", "ABS", "DATE", "DATETIME", "STRFTIME", "TOTAL",
    "GROUP_CONCAT", "IIF", "RANK", "ROW_NUMBER", "DENSE_RANK",
}
_NO_SPACE_BEFORE_PAREN = {"CAST"}
_JOIN_MODS = {"NATURAL", "LEFT", "RIGHT", "INNER", "FULL", "CROSS", "OUTER"}
_SIMPLE_CLAUSES = {
    "SELECT", "FROM", "WHERE", "HAVING", "LIMIT", "OFFSET", "VALUES", "SET", "UPDATE", "INTERSECT", "EXCEPT",
}
_FMT_TOKEN = re.compile(
    r"""(?P<ws>\s+)
    |(?P<comment>--[^\n]*|/\*.*?\*/)
    |(?P<string>'(?:[^']|'')*')
    |(?P<qid>"(?:[^"]|"")*"|`[^`]*`)
    |(?P<number>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)
    |(?P<word>[A-Za-z_][A-Za-z_0-9$]*)
    |(?P<op><=|>=|<>|!=|==|\|\||[(),.;*/%+\-<>=])""",
    re.X | re.S,
)


def _tokenize(sql: str):
    toks, pos = [], 0
    for m in _FMT_TOKEN.finditer(sql):
        if m.start() != pos:
            raise ValueError("unsupported character")
        pos = m.end()
        kind = m.lastgroup
        if kind == "ws":
            continue
        if kind == "comment":
            raise ValueError("comments are left untouched")
        toks.append((kind, m.group()))
    if pos != len(sql):
        raise ValueError("unsupported character")
    return toks


def _nest(toks):
    root, stack, cur = [], [], None
    cur = root
    for t in toks:
        if t == ("op", "("):
            group = []
            cur.append(("group", group))
            stack.append(cur)
            cur = group
        elif t == ("op", ")"):
            if not stack:
                raise ValueError("unbalanced parentheses")
            cur = stack.pop()
        else:
            cur.append(t)
    if stack:
        raise ValueError("unbalanced parentheses")
    return root


def _w(item):
    return item[1].upper() if item[0] == "word" else None


def _is_op(item, symbol):
    return item[0] == "op" and item[1] == symbol


def _split_commas(items):
    parts, cur = [], []
    for it in items:
        if _is_op(it, ","):
            parts.append(cur)
            cur = []
        else:
            cur.append(it)
    parts.append(cur)
    return parts


def _split_conditions(items):
    out, cur, conn = [], [], ""
    between = case = 0
    for it in items:
        w = _w(it)
        if w == "CASE":
            case += 1
        elif w == "END" and case:
            case -= 1
        elif w == "BETWEEN":
            between += 1
        elif w in ("AND", "OR") and not case:
            if w == "AND" and between:
                between -= 1
            else:
                out.append((conn, cur))
                cur, conn = [], w
                continue
        cur.append(it)
    out.append((conn, cur))
    return out


def _clause_at(items, i):
    if i > 0 and _is_op(items[i - 1], "."):
        return None
    w = _w(items[i])
    if w is None:
        return None
    nxt = _w(items[i + 1]) if i + 1 < len(items) else None
    if w in ("GROUP", "ORDER") and nxt == "BY":
        return f"{w} BY", 2
    if w == "DELETE" and nxt == "FROM":
        return "DELETE FROM", 2
    if w == "INSERT" and nxt == "INTO":
        return "INSERT INTO", 2
    if w == "UNION":
        return ("UNION ALL", 2) if nxt == "ALL" else ("UNION", 1)
    if w in _JOIN_MODS or w == "JOIN":
        j = i
        while j < len(items) and _w(items[j]) in _JOIN_MODS:
            j += 1
        if j < len(items) and _w(items[j]) == "JOIN":
            return " ".join(_w(x) for x in items[i:j + 1]), j + 1 - i
        return None
    if w == "WITH" and i == 0:
        return "WITH", 1
    if w in _SIMPLE_CLAUSES:
        return w, 1
    return None


def _tok_text(items, k):
    kind, text = items[k]
    if kind != "word" or (k > 0 and _is_op(items[k - 1], ".")):
        return text
    up = text.upper()
    if up in _FMT_KEYWORDS:
        return up
    if up in _FUNC_UPPER and k + 1 < len(items) and items[k + 1][0] == "group":
        return up
    return text


def _is_unary(items, k):
    if k == 0:
        return True
    prev = items[k - 1]
    if prev[0] == "op":
        return True
    if prev[0] == "word":
        return prev[1].upper() in _FMT_KEYWORDS
    return False


def _space_before_group(prev) -> bool:
    if prev[0] == "word":
        up = prev[1].upper()
        return up in _FMT_KEYWORDS and up not in _NO_SPACE_BEFORE_PAREN
    if prev[0] == "op":
        return prev[1] != "."
    return True


def _inline(items, indent: int) -> str:
    pad = " " * indent
    out, prev, glue = [], None, False
    for k, it in enumerate(items):
        if it[0] == "group":
            inner = it[1]
            if inner and _w(inner[0]) in ("SELECT", "WITH"):
                text = "(\n" + "\n".join(_format_items(inner, indent + 4)) + "\n" + pad + ")"
            else:
                text = "(" + _inline(inner, indent) + ")"
            if prev is not None and not glue and _space_before_group(prev):
                out.append(" ")
            out.append(text)
            glue = False
        elif _is_op(it, ",") or _is_op(it, ";"):
            out.append(it[1])
            glue = False
        elif _is_op(it, "."):
            out.append(".")
            glue = True
        else:
            if prev is not None and not glue:
                out.append(" ")
            out.append(_tok_text(items, k))
            glue = it[0] == "op" and it[1] in "+-" and _is_unary(items, k)
        prev = it
    return "".join(out)


def _cond_lines(prefix, conds, indent, cont_indent):
    out = []
    for n, (conn, items) in enumerate(conds):
        text = _inline(items, cont_indent if n else indent)
        if n == 0:
            out.append(" " * indent + prefix + " " + text)
        else:
            out.append(" " * cont_indent + conn + " " + text)
    return out


def _break_list(head, parts, indent):
    pad, sub = " " * indent, " " * (indent + 4)
    out = [pad + head]
    for n, p in enumerate(parts):
        out.append(sub + _inline(p, indent + 4) + ("," if n < len(parts) - 1 else ""))
    return out


def _render_clause(head, body, indent):
    pad = " " * indent
    if not head:
        return [pad + _inline(body, indent)]
    if not body:
        return [pad + head]

    if head == "SELECT":
        mod = ""
        if _w(body[0]) in ("DISTINCT", "ALL"):
            mod, body = " " + _w(body[0]), body[1:]
        parts = _split_commas(body)
        texts = [_inline(p, indent + 4) for p in parts]
        joined = ", ".join(texts)
        if len(parts) == 1:
            return [pad + "SELECT" + mod + " " + _inline(body, indent)]
        if len(parts) <= 3 and len(joined) <= 60 and "\n" not in joined:
            return [pad + "SELECT" + mod + " " + joined]
        return _break_list("SELECT" + mod, parts, indent)

    if head in ("FROM", "SET"):
        parts = _split_commas(body)
        if len(parts) == 1:
            return [pad + head + " " + _inline(body, indent)]
        return _break_list(head, parts, indent)

    if "JOIN" in head:
        idx = next((k for k, it in enumerate(body) if _w(it) in ("ON", "USING")), None)
        if idx is None:
            return [pad + head + " " + _inline(body, indent)]
        out = [pad + head + " " + _inline(body[:idx], indent)]
        cond = body[idx:]
        if _w(cond[0]) == "ON":
            out += _cond_lines("ON", _split_conditions(cond[1:]), indent + 4, indent + 4)
        else:
            out.append(pad + "    " + _inline(cond, indent + 4))
        return out

    if head in ("WHERE", "HAVING"):
        return _cond_lines(head, _split_conditions(body), indent, indent + 4)

    if head in ("GROUP BY", "ORDER BY"):
        parts = _split_commas(body)
        one = head + " " + ", ".join(_inline(p, indent + 4) for p in parts)
        if len(parts) == 1 or (len(one) <= 72 and "\n" not in one):
            return [pad + one]
        return _break_list(head, parts, indent)

    if head == "WITH":
        texts = [_inline(p, indent) for p in _split_commas(body)]
        return [pad + "WITH " + (",\n" + pad).join(texts)]

    return [pad + head + " " + _inline(body, indent)]


def _format_items(items, indent):
    clauses, head, body, i = [], "", [], 0
    while i < len(items):
        found = _clause_at(items, i)
        if found:
            if head or body:
                clauses.append((head, body))
            head, body = found[0], []
            i += found[1]
        else:
            body.append(items[i])
            i += 1
    if head or body:
        clauses.append((head, body))
    lines = []
    for h, b in clauses:
        lines.extend(_render_clause(h, b, indent))
    return lines


def format_sql(sql: str) -> str:
    original = re.sub(r"\n\s*\n+", "\n", (sql or "").strip())
    if not original:
        return original
    try:
        tree = _nest(_tokenize(original))
        stmts, cur = [], []
        for it in tree:
            if _is_op(it, ";"):
                stmts.append((cur, True))
                cur = []
            else:
                cur.append(it)
        if cur:
            stmts.append((cur, False))
        chunks = []
        for items, semi in stmts:
            if not items:
                continue
            chunks.append("\n".join(_format_items(items, 0)) + (";" if semi else ""))
        return "\n".join(chunks) or original
    except Exception:
        return original


# --------------------------------------------------------------------------- #
# HTML builders
# --------------------------------------------------------------------------- #
def esc(text) -> str:
    return html.escape(str(text)) if text is not None else ""


def highlight_sql(sql: str, pretty: bool = True, wrap: bool = False) -> str:
    sql = format_sql(sql) if pretty else re.sub(r"\n\s*\n+", "\n", sql.strip())
    out, pos = [], 0
    for m in _TOKEN.finditer(sql):
        out.append(html.escape(sql[pos:m.start()]))
        text, kind = m.group(), m.lastgroup
        if kind == "word":
            if text.upper() in SQL_KEYWORDS:
                kind = "kw"
            elif sql[m.end():m.end() + 1] == "(":
                kind = "fn"
            else:
                kind = "id"
        elif kind == "string":
            kind = "str"
        elif kind == "number":
            kind = "num"
        elif kind == "qid":
            kind = "id"
        out.append(f'<span class="t-{kind}">{html.escape(text)}</span>')
        pos = m.end()
    out.append(html.escape(sql[pos:]))
    cls = "sql wrap" if wrap else "sql"
    return f'<pre class="{cls}">' + "".join(out) + "</pre>"


def code_card(label: str, sql: str, pretty: bool = True, wrap: bool = False) -> str:
    body = highlight_sql(sql, pretty=pretty, wrap=wrap)
    card = f'<div class="codecard"><div class="codehead"><span class="lang">{esc(label)}</span></div>{body}</div>'
    return re.sub(r"\n\s*\n+", "\n", card)


def _fmt_cell(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return '<span class="null">—</span>'
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        return f"{v:,.2f}"
    return esc(v)


def html_table(rows, max_rows: int = 500) -> str:
    if not rows:
        return ""
    df = pd.DataFrame(rows)
    shown = df.head(max_rows)
    numeric = {c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])}
    head = "".join(
        f'<th class="{"num" if c in numeric else ""}">{esc(c)}</th>' for c in df.columns
    )
    body_parts = []
    for rec in shown.astype(object).where(shown.notna(), None).to_dict("records"):
        cells = "".join(
            f'<td class="{"num" if c in numeric else ""}">{_fmt_cell(rec[c])}</td>' for c in df.columns
        )
        body_parts.append(f"<tr>{cells}</tr>")
    note = ""
    if len(df) > max_rows:
        note = f'<div class="tbl-note">Showing first {max_rows} of {len(df)} rows. Download the CSV for the full dataset.</div>'
    return (
        f'<div class="tbl-wrap"><table class="tbl"><thead><tr>{head}</tr></thead>'
        f'<tbody>{"".join(body_parts)}</tbody></table></div>{note}'
    )


def bars_html(df: pd.DataFrame):
    if df is None or df.empty or not (2 <= len(df) <= 25):
        return None
    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    labels = [c for c in df.columns if c not in numeric]
    if not numeric or not labels:
        return None
    val_col, label_col = numeric[-1], labels[0]
    vals = pd.to_numeric(df[val_col], errors="coerce").fillna(0)
    if (vals < 0).any() or vals.max() <= 0:
        return None
    top = float(vals.max())
    rows = []
    for lab, v in zip(df[label_col], vals):
        pct = max(3.0, float(v) / top * 100)
        shown = f"{v:,.2f}" if not float(v).is_integer() else f"{int(v):,}"
        rows.append(
            f'<div class="bar-row"><div class="bar-label" title="{esc(lab)}">{esc(lab)}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{pct:.1f}%"></div></div>'
            f'<div class="bar-val">{shown}</div></div>'
        )
    return f'<div class="bars"><div class="bars-title">{esc(val_col)} by {esc(label_col)}</div>{"".join(rows)}</div>'


def pipeline_html(run) -> str:
    if not run:
        return ""
    stages = [
        ("gen", "Write SQL", "Question to query"),
        ("val", "Check guardrails", "AST validation"),
        ("exec", "Run read-only", "Sandboxed SQLite"),
    ]
    labels = {"ok": "Complete", "fail": "Stopped here", "skip": "Not run", "run": "In progress"}
    parts = []
    for n, (key, title, idle) in enumerate(stages, start=1):
        state = run.get(key)
        num = "✓" if state == "ok" else "✕" if state == "fail" else str(n)
        parts.append(
            f'<div class="pipe-step {state or ""}"><div class="pipe-num">{num}</div>'
            f'<div><div class="pipe-name">{title}</div><div class="pipe-state">{labels.get(state, idle)}</div></div></div>'
        )
    return f'<div class="pipe">{"".join(parts)}</div>'


def live_run(stage: str) -> dict:
    order = ["gen", "val", "exec"]
    idx = order.index(stage) if stage in order else 0
    return {k: ("ok" if i < idx else "run" if i == idx else None) for i, k in enumerate(order)}


# --------------------------------------------------------------------------- #
# Background pipeline
# --------------------------------------------------------------------------- #
def run_pipeline(question, api_key, model, force_mock, state):
    run = {"gen": None, "val": None, "exec": None}
    try:
        state["stage"] = "gen"
        direct = question.strip().upper().startswith(RAW_SQL_PREFIXES)
        is_mock, gen_error = False, None
        if direct:
            sql = question.strip()
        else:
            gen = generate_sql_query(
                user_question=question, api_key=api_key, model_name=model, force_mock=force_mock
            )
            sql, is_mock, gen_error = gen.sql, gen.is_mock, gen.error_message
        run["gen"] = "ok" if sql else "fail"
        if state["cancel"].is_set():
            return

        state["stage"] = "val"
        val = validate_and_sanitize_sql(
            sql_text=sql,
            schema_columns=get_table_columns_map(DATABASE_PATH),
            default_limit=DEFAULT_ROW_LIMIT,
            max_limit=MAX_ROW_LIMIT,
        )
        run["val"] = "ok" if val.is_valid else "fail"
        validation = {
            "is_valid": val.is_valid,
            "error_message": val.error_message,
            "warnings": val.warnings,
            "sanitized_sql": getattr(val, "sanitized_sql", None),
        }
        results, metrics, reply = None, None, ""
        if not val.is_valid:
            run["exec"] = "skip"
            reply = f"**Blocked for security.** {val.error_message}\n\nNo statements were executed against the database."
        else:
            if state["cancel"].is_set():
                return
            state["stage"] = "exec"
            ex = execute_read_only_query(sql_query=val.sanitized_sql, db_path=DATABASE_PATH)
            if ex.success:
                run["exec"] = "ok"
                results = ex.rows
                metrics = {
                    "execution_time_ms": ex.execution_time_ms,
                    "row_count": ex.row_count,
                    "truncated": ex.truncated,
                }
                reply = (
                    f"Successfully retrieved **{ex.row_count}** rows." if results else "The query executed successfully but returned 0 rows."
                )
            else:
                run["exec"] = "fail"
                reply = f"**Query execution failed.** {ex.error_message}"

        state["result"] = {
            "role": "assistant",
            "content": reply,
            "sql": sql,
            "validation": validation,
            "results": results,
            "metrics": metrics,
            "is_mock": is_mock,
            "direct": direct,
            "gen_error": gen_error,
            "run": run,
        }
    except Exception as exc:
        state["error"] = str(exc)
    finally:
        state["done"] = True


# --------------------------------------------------------------------------- #
# Assistant message rendering
# --------------------------------------------------------------------------- #
def render_assistant(msg: dict, idx: int):
    val = msg.get("validation") or {}
    sql = msg.get("sql")

    if msg.get("stopped"):
        st.markdown(
            '<div class="verdict warn"><div class="mark">■</div><div><b>Request cancelled</b>'
            "<span>You cancelled this request. No actions were performed on the database.</span></div></div>",
            unsafe_allow_html=True,
        )
        return
    if msg.get("failed"):
        st.markdown(
            '<div class="verdict bad"><div class="mark">✕</div><div><b>Execution error</b>'
            f"<span>{esc(msg.get('content'))}</span></div></div>",
            unsafe_allow_html=True,
        )
        return

    if msg.get("content"):
        st.markdown(msg["content"])
    if not sql:
        return

    if val.get("is_valid"):
        st.markdown(
            '<div class="verdict ok"><div class="mark">✓</div><div><b>Guardrail approved: read-only SELECT</b>'
            "<span>Passed strict AST verification for allowed statement types, tables, columns, and row limits.</span></div></div>",
            unsafe_allow_html=True,
        )
        for w in val.get("warnings") or []:
            st.markdown(
                f'<div class="verdict warn"><div class="mark">!</div><div><span>{esc(w)}</span></div></div>',
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            '<div class="verdict bad"><div class="mark">✕</div><div><b>Blocked by guardrails</b>'
            f'<span>{esc(val.get("error_message"))}</span></div></div>',
            unsafe_allow_html=True,
        )
    if msg.get("gen_error"):
        st.caption(f"Generator note: {msg['gen_error']}")

    sanitized = val.get("sanitized_sql")
    changed = bool(val.get("is_valid") and sanitized and sanitized.strip() != sql.strip())
    if changed:
        st.markdown(code_card("Generated SQL", sql), unsafe_allow_html=True)
        st.markdown(code_card("Executed SQL (after guardrail rewrite)", sanitized), unsafe_allow_html=True)
    else:
        st.markdown(code_card("SQL", sql), unsafe_allow_html=True)
    with st.expander("Copy SQL"):
        st.code(format_sql(sanitized if changed else sql), language="sql")

    if not val.get("is_valid"):
        return
    results = msg.get("results")
    if results is None:
        return

    metrics = msg.get("metrics") or {}
    chips = (
        f'<span class="chip"><b>{metrics.get("row_count", 0)}</b> rows</span>'
        f'<span class="chip"><b>{metrics.get("execution_time_ms", 0)}</b> ms</span>'
        '<span class="chip">Sandboxed connection</span>'
    )
    if metrics.get("truncated"):
        chips += f'<span class="chip warn">Capped at {MAX_ROW_LIMIT} rows</span>'
    if msg.get("is_mock") and not msg.get("direct"):
        chips += '<span class="chip warn">Offline mock generator</span>'
    st.markdown(f'<div class="chips">{chips}</div>', unsafe_allow_html=True)

    if not results:
        st.info("The query executed successfully but returned 0 rows.")
        return

    df = pd.DataFrame(results)
    bars = bars_html(df)
    if bars:
        tab_table, tab_chart = st.tabs(["Table", "Bar chart"])
        with tab_table:
            st.markdown(html_table(results), unsafe_allow_html=True)
        with tab_chart:
            st.markdown(bars, unsafe_allow_html=True)
    else:
        st.markdown(html_table(results), unsafe_allow_html=True)

    st.download_button(
        "⬇ Download CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=f"query_result_{idx}.csv",
        mime="text/csv",
        key=f"dl_{idx}",
    )


# --------------------------------------------------------------------------- #
# State Initialization
# --------------------------------------------------------------------------- #
if not DATABASE_PATH.exists():
    with st.spinner("Initializing sample database..."):
        populate_default_database(seed=42, db_path=DATABASE_PATH)

st.session_state.setdefault("messages", [])
st.session_state.setdefault("pending_prompt", None)
st.session_state.setdefault("last_run", None)
st.session_state.setdefault("job", None)


def cancel_job():
    job = st.session_state.job
    if job:
        job["cancel"].set()
    st.session_state.job = None


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown(
        '<div class="brand"><div class="logo">✦</div><div class="brand-name">Guarded SQL</div></div>',
        unsafe_allow_html=True,
    )

    if st.button("＋  New chat", use_container_width=True, key="new_chat"):
        cancel_job()
        st.session_state.messages = []
        st.session_state.last_run = None
        st.rerun()

    st.markdown('<div class="side-heading">Model</div>', unsafe_allow_html=True)
    with st.expander("Model settings"):
        api_key_input = st.text_input(
            "Gemini API Key",
            value=GEMINI_API_KEY,
            type="password",
            help="Leave blank to use .env or offline mock mode.",
        )
        force_mock = st.toggle(
            "Offline Mock Mode",
            value=not bool(api_key_input),
            help="Use deterministic local generator instead of Gemini API.",
        )
        model_choice = st.selectbox(
            "Gemini Model",
            options=[
                "gemini-3.8-flash",
                "gemini-3.7-flash",
                "gemini-3.5-flash",
                "gemini-2.0-flash",
                "gemini-1.5-flash",
                "gemini-2.5-pro",
            ],
            index=0,
            disabled=force_mock,
        )

    st.markdown('<div class="side-heading">Database</div>', unsafe_allow_html=True)
    row_counts = get_table_row_counts(DATABASE_PATH)
    st.markdown(
        "".join(
            f'<div class="table-row"><span class="tn">{esc(t)}</span><span class="tc">{c:,} rows</span></div>'
            for t, c in row_counts.items()
        ),
        unsafe_allow_html=True,
    )
    st.markdown('<div style="height:.5rem"></div>', unsafe_allow_html=True)

    with st.expander("Browse table columns"):
        table_selected = st.selectbox("Select Table", options=list(ALLOWED_TABLES))
        sample_rows = get_sample_rows(DATABASE_PATH, table_name=table_selected, limit=3)
        if sample_rows:
            st.markdown('<div class="panel-title">Sample rows</div>', unsafe_allow_html=True)
            st.markdown(html_table(sample_rows, max_rows=3), unsafe_allow_html=True)
        schema_summary = get_schema_summary(DATABASE_PATH)
        st.markdown('<div class="panel-title">Schema</div>', unsafe_allow_html=True)
        st.markdown(code_card("Schema", schema_summary, pretty=False, wrap=True), unsafe_allow_html=True)

    st.markdown('<div class="side-heading">Quick prompts</div>', unsafe_allow_html=True)
    for q in EXAMPLE_QUESTIONS:
        if st.button(q, use_container_width=True, key=f"side_ex_{q}", help=q):
            st.session_state.pending_prompt = q

    st.markdown('<div class="side-heading">Data</div>', unsafe_allow_html=True)
    if st.button("↻  Reset sample database", use_container_width=True, key="reset_db", help="Re-seed sample database."):
        populate_default_database(seed=42, db_path=DATABASE_PATH)
        st.success("Re-seeded!")
        time.sleep(0.8)
        st.rerun()

# --------------------------------------------------------------------------- #
# Top bar
# --------------------------------------------------------------------------- #
try:
    bar_left, bar_right = st.columns([5, 1.6], vertical_alignment="center")
except TypeError:
    bar_left, bar_right = st.columns([5, 1.6])

with bar_left:
    pill = "Offline mock" if force_mock else model_choice
    st.markdown(
        '<div class="topbar"><span class="topbar-title">Guarded SQL Assistant</span>'
        f'<span class="model-pill">{esc(pill)}</span></div>',
        unsafe_allow_html=True,
    )

pipe_slot = st.empty()


def show_pipeline(run):
    markup = pipeline_html(run)
    if markup:
        pipe_slot.markdown(markup, unsafe_allow_html=True)
    else:
        pipe_slot.empty()


show_pipeline(st.session_state.last_run)

# --------------------------------------------------------------------------- #
# Chat History or Hero State
# --------------------------------------------------------------------------- #
job = st.session_state.job
user_input = None

if not st.session_state.messages:
    st.markdown(
        '<div class="hero"><div class="hero-spark">✦</div>'
        '<h1 class="hero-title">Where should we start?</h1>'
        '<p class="hero-sub">Ask about customers, products, or orders in plain English. '
        "Every query is checked by AST guardrails and runs read-only.</p></div>",
        unsafe_allow_html=True,
    )

    with st.container():
        user_input = st.chat_input("Ask a question about customers, products, or orders...", key="hero_chat_input")

    st.markdown('<div class="section-title">Try asking</div>', unsafe_allow_html=True)
    cols = st.columns(2)
    for i, q in enumerate(EXAMPLE_QUESTIONS):
        with cols[i % 2]:
            if st.button(q, use_container_width=True, key=f"hero_ex_{i}"):
                st.session_state.pending_prompt = q

    st.markdown('<div class="section-title">Security guardrail tests</div>', unsafe_allow_html=True)
    cols = st.columns(2)
    for i, q in enumerate(SECURITY_TESTS):
        with cols[i % 2]:
            if st.button(q, use_container_width=True, key=f"hero_sec_{i}"):
                st.session_state.pending_prompt = q
else:
    for i, msg in enumerate(st.session_state.messages):
        if msg["role"] == "user":
            with st.chat_message("user"):
                st.markdown(f'<div class="user-q">{esc(msg["content"])}</div>', unsafe_allow_html=True)
        else:
            with st.chat_message("assistant", avatar="🛡️"):
                render_assistant(msg, i)

# --------------------------------------------------------------------------- #
# Active In-Flight Request Handling with Integrated Stop Button
# --------------------------------------------------------------------------- #
if job:
    with st.chat_message("assistant", avatar="🛡️"):
        stage_text = {
            "gen": "Writing SQL query via LLM...",
            "val": "Checking AST security guardrails...",
            "exec": "Running sandboxed read-only query...",
        }.get(job["stage"], "Working...")

        elapsed = time.time() - job["t0"]

        try:
            col_live_info, col_live_btn = st.columns([4, 1.2], vertical_alignment="center")
        except TypeError:
            col_live_info, col_live_btn = st.columns([4, 1.2])
        with col_live_info:
            st.markdown(
                f'<div class="live"><div class="spin"></div>'
                f'<div><div class="live-title">{stage_text}</div>'
                f'<div class="live-sub">{elapsed:0.1f}s elapsed</div></div></div>',
                unsafe_allow_html=True,
            )
        with col_live_btn:
            stop_clicked = st.button("■  Stop", key="stop_btn", type="primary", use_container_width=True)

    if stop_clicked:
        cancel_job()
        st.session_state.messages.append(
            {"role": "assistant", "content": "", "stopped": True}
        )
        st.session_state.last_run = None
        st.rerun()

    st.chat_input("Pipeline running... Click Stop to cancel.", disabled=True)

    # Let background execution complete naturally without continuous full page re-runs causing layout flashing
    while not job["done"]:
        time.sleep(0.1)
        show_pipeline(live_run(job["stage"]))

    if job.get("error"):
        st.session_state.messages.append(
            {"role": "assistant", "content": job["error"], "failed": True}
        )
        st.session_state.last_run = {"gen": "fail", "val": None, "exec": None}
    else:
        result = job["result"]
        st.session_state.last_run = result.pop("run")
        st.session_state.messages.append(result)
    st.session_state.job = None
    st.rerun()

# --------------------------------------------------------------------------- #
# Chat Input Bar
# --------------------------------------------------------------------------- #
busy = st.session_state.job is not None
if st.session_state.messages or busy:
    user_input = st.chat_input("Ask a question about customers, products, or orders...", disabled=busy, key="dock_chat_input")

if st.session_state.pending_prompt:
    if not busy:
        user_input = st.session_state.pending_prompt
    st.session_state.pending_prompt = None

if user_input and not busy:
    st.session_state.messages.append({"role": "user", "content": user_input})
    state = {
        "stage": "gen",
        "done": False,
        "cancel": threading.Event(),
        "t0": time.time(),
        "result": None,
        "error": None,
    }
    threading.Thread(
        target=run_pipeline,
        args=(user_input, api_key_input, model_choice, force_mock, state),
        daemon=True,
    ).start()
    st.session_state.job = state
    st.rerun()