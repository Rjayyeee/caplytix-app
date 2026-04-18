import sqlite3
import json
import base64
from datetime import date, datetime
from pathlib import Path
from html import escape
from typing import Dict, List

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = str(BASE_DIR / "caplytix.db")
APP_NAME = "Caplytix Arena"
APP_TAGLINE = "Performance Intelligence for Serious Traders."
LOGO_PATH = BASE_DIR / "caplytix_arena_logo2.png"
PAGE_ICON = BASE_DIR / "Caplytix_icon.png"

st.set_page_config(
    page_title=APP_NAME,
    page_icon=str(PAGE_ICON) if PAGE_ICON.exists() else "📈",
    layout="wide",
)

# -----------------------------
# Constants
# -----------------------------
PAGES = [
    "Dashboard",
    "Daily Performance",
    "Performance History",
    "Trade Journal",
    "Trade History",
    "Growth Projection",
    "AI Psychology Review",
    "Settings",
]

MISTAKE_TAGS_BY_CATEGORY: Dict[str, Dict[str, int]] = {
    "Execution": {
        "Chased Entry": 8,
        "Late Exit": 7,
        "Early Exit": 5,
        "Poor Fill / Slippage": 3,
    },
    "Risk Management": {
        "Oversized Position": 12,
        "No Defined Risk": 12,
        "Moved Stop": 10,
        "Added to Loser": 11,
    },
    "Process": {
        "No Plan": 12,
        "Ignored Setup Rules": 9,
        "Forced Trade": 8,
        "Overtraded": 9,
    },
    "Psychology": {
        "Revenge Trade": 12,
        "FOMO": 8,
        "Impatience": 6,
        "Loss of Focus": 6,
    },
}

EDGE_TAGS_BY_CATEGORY: Dict[str, Dict[str, int]] = {
    "Execution": {
        "Precise Entry": 5,
        "Clean Exit": 5,
        "Followed Levels": 4,
        "Waited for Confirmation": 5,
    },
    "Risk Management": {
        "Proper Size": 7,
        "Respected Stop": 7,
        "Managed Risk Well": 6,
        "Protected Gains": 5,
    },
    "Process": {
        "Had Clear Plan": 7,
        "A+ Setup": 8,
        "Patient Entry": 6,
        "Good Review Notes": 4,
    },
    "Psychology": {
        "Stayed Disciplined": 8,
        "Emotion Controlled": 7,
        "Accepted Loss Well": 5,
        "Consistent Routine": 4,
    },
}

TRADE_TYPES = ["Shares", "Options"]
DIRECTIONS = ["Long", "Short"]
OPTION_SIDES = ["Call", "Put"]
TRACKING_PRESETS = {
    "252 Trading Days": 252,
    "365 Calendar Days": 365,
    "Custom": None,
}


# -----------------------------
# Database helpers
# -----------------------------
@st.cache_resource
def get_conn():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT NOT NULL,
            user_email TEXT NOT NULL,
            value TEXT NOT NULL,
            PRIMARY KEY (key, user_email)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_performance (
            trade_date TEXT NOT NULL,
            user_email TEXT NOT NULL,
            deposit REAL NOT NULL DEFAULT 0,
            withdrawal REAL NOT NULL DEFAULT 0,
            daily_pnl REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (trade_date, user_email)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS trade_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            trade_type TEXT NOT NULL,
            direction TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 0,
            entry_price REAL NOT NULL DEFAULT 0,
            exit_price REAL NOT NULL DEFAULT 0,
            option_side TEXT,
            strike REAL,
            expiration_date TEXT,
            mistake_categories TEXT NOT NULL DEFAULT '[]',
            mistake_tags TEXT NOT NULL DEFAULT '[]',
            edge_categories TEXT NOT NULL DEFAULT '[]',
            edge_tags TEXT NOT NULL DEFAULT '[]',
            discipline_score REAL NOT NULL DEFAULT 100,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    conn.commit()


def get_setting(key: str, user_email: str, default: str = "") -> str:
    conn = get_conn()
    row = conn.execute(
        "SELECT value FROM settings WHERE key = ? AND user_email = ?",
        (key, user_email),
    ).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str, user_email: str):
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO settings (key, user_email, value)
        VALUES (?, ?, ?)
        ON CONFLICT(key, user_email) DO UPDATE SET value = excluded.value
        """,
        (key, user_email, value),
    )
    conn.commit()


def load_settings(user_email: str) -> Dict[str, object]:
    preset = get_setting("tracking_preset", user_email, "252 Trading Days")
    days = int(float(get_setting("tracking_days", user_email, "252")))
    return {
        "starting_balance": float(get_setting("starting_balance", user_email, "1000")),
        "tracking_preset": preset,
        "tracking_days": days,
        "projection_method": get_setting("projection_method", user_email, "Average Daily %"),
    }


def reset_table(table_name: str, user_email: str):
    conn = get_conn()
    conn.execute(f"DELETE FROM {table_name} WHERE user_email = ?", (user_email,))
    conn.commit()


# -----------------------------
# Utility helpers
# -----------------------------
def fmt_money(v) -> str:
    try:
        return f"${float(v):,.2f}"
    except Exception:
        return "$0.00"


def fmt_pct(v) -> str:
    try:
        return f"{float(v) * 100:,.2f}%"
    except Exception:
        return "0.00%"


def clamp(v: float, low: float, high: float) -> float:
    return max(low, min(high, v))


def json_dumps_list(values: List[str]) -> str:
    return json.dumps(values or [])


def json_loads_list(value: str) -> List[str]:
    try:
        data = json.loads(value or "[]")
        if isinstance(data, list):
            return [str(x) for x in data]
    except Exception:
        pass
    return []


def get_logo_path() -> str | None:
    return str(LOGO_PATH) if Path(LOGO_PATH).exists() else None


def img_file_to_base64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def render_sidebar_logo():
    logo_path = get_logo_path()
    if not logo_path:
        return
    logo_b64 = img_file_to_base64(logo_path)
    st.markdown(
        f"""
        <div class="ca-sidebar-brand-wrap">
            <img src="data:image/png;base64,{logo_b64}" class="ca-sidebar-logo-full" />
        </div>
        """,
        unsafe_allow_html=True,
    )


def _get_query_params() -> dict:
    try:
        return {k: v for k, v in st.query_params.items()}
    except Exception:
        try:
            return st.experimental_get_query_params()
        except Exception:
            return {}


# -----------------------------
# Auth helpers
# -----------------------------
def get_allowed_users() -> set:
    try:
        users = st.secrets["app"]["allowed_users"]
        return {str(x).strip().lower() for x in users if str(x).strip()}
    except Exception:
        return set()


def get_current_user_email() -> str:
    try:
        if st.user.is_logged_in:
            return str(getattr(st.user, "email", "") or "").strip().lower()
    except Exception:
        pass
    return ""


def is_allowed_user() -> bool:
    email = get_current_user_email()
    return bool(email) and email in get_allowed_users()


# -----------------------------
# Landing + Login pages
# -----------------------------
def render_landing_page():
    logo_path = get_logo_path()
    logo_html = ""
    if logo_path:
        logo_b64 = img_file_to_base64(logo_path)
        logo_html = f'<img src="data:image/png;base64,{logo_b64}" class="ca-logo" style="max-width:420px;display:block;margin:0 auto 1rem auto;" />'

    st.markdown(
        f"""
        <div class="ca-landing-outer">
            <div class="ca-landing-card">
                {logo_html}
                <div class="ca-tagline">{APP_TAGLINE}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("ENTER THE ARENA", key="landing_enter", use_container_width=True):
            try:
                st.query_params["view"] = "login"
            except Exception:
                st.experimental_set_query_params(view="login")
            st.rerun()


def render_login_page():
    logo_path = get_logo_path()
    logo_b64_tag = ""
    if logo_path:
        logo_b64 = img_file_to_base64(logo_path)
        logo_b64_tag = f'<img src="data:image/png;base64,{logo_b64}" class="ca-logo" style="max-width:320px;display:block;margin:0 auto 1rem auto;" />'

    st.markdown(
        f"""
        <style>
        .ca-login-shell {{
            min-height: 60vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding-bottom: 0.5rem;
        }}
        .ca-login-card {{
            width: 100%;
            max-width: 760px;
            text-align: center;
            padding: 2rem 1.5rem 1.6rem 1.5rem;
            border-radius: 30px;
            background:
                radial-gradient(circle at center, rgba(126,232,255,0.06), transparent 24%),
                linear-gradient(135deg, rgba(3,10,24,0.98), rgba(6,18,42,0.95));
            border: 1px solid rgba(126,232,255,0.10);
            box-shadow: 0 18px 50px rgba(0,0,0,0.40);
        }}
        .ca-login-title {{
            color: #eef4ff;
            font-size: 2.5rem !important;
            font-weight: 900 !important;
            letter-spacing: 0.08em !important;
            margin-top: 0.25rem;
            margin-bottom: 0.5rem;
        }}
        div[data-testid="stHorizontalBlock"] {{
            margin-top: -1.5rem !important;
        }}
        div[data-testid="stVerticalBlock"] .stButton {{
            margin-top: 0 !important;
            margin-bottom: 0 !important;
            padding-top: 0 !important;
            padding-bottom: 0 !important;
        }}
        div[data-testid="stVerticalBlock"] .stButton:last-of-type > button {{
            color: #ffffff !important;
            font-weight: 700 !important;
            text-transform: none !important;
            letter-spacing: 0.03em !important;
        }}
        </style>
        <div class="ca-login-shell">
            <div class="ca-login-card">
                {logo_b64_tag}
                <div class="ca-tagline">{APP_TAGLINE}</div>
                <div class="ca-login-title">PRIVATE ACCESS</div>
                <div class="ca-login-subtitle">
                    Sign in with your approved Google account to enter Caplytix.
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    left, center, right = st.columns([1.15, 1.7, 1.15])
    with center:
        components.html(
            """
            <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                background: transparent;
                overflow: visible;
                padding-top: 4px;
            }
            .google-btn {
                width: 100%;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 0.35rem;
                background: linear-gradient(180deg, rgba(10,24,50,0.95), rgba(4,12,28,0.95));
                border: 1px solid rgba(126,232,255,0.20);
                border-radius: 14px;
                padding: 0.7rem 1rem;
                cursor: pointer;
                box-shadow: 0 8px 20px rgba(0,0,0,0.22);
                font-family: Arial, sans-serif;
                font-size: 1rem;
                font-weight: 700;
                color: #eef4ff;
                transition: border-color 0.2s ease, box-shadow 0.2s ease;
                text-transform: none;
                letter-spacing: 0.01em;
            }
            .google-btn:hover {
                border-color: rgba(126,232,255,0.35);
                box-shadow: 0 0 0 1px rgba(126,232,255,0.05), 0 10px 24px rgba(0,0,0,0.30);
            }
            .g-word {
                font-size: 1.05rem;
                font-weight: 900;
                font-family: Arial, sans-serif;
                letter-spacing: 0.02em;
            }
            .g-blue   { color: #4285F4; }
            .g-red    { color: #EA4335; }
            .g-yellow { color: #FBBC05; }
            .g-green  { color: #34A853; }
            </style>

            <div class="google-btn" id="gBtn">
                Log in with&nbsp;
                <span class="g-word">
                    <span class="g-blue">G</span><span class="g-red">o</span><span class="g-yellow">o</span><span class="g-blue">g</span><span class="g-green">l</span><span class="g-red">e</span>
                </span>
            </div>

            <script>
            document.getElementById('gBtn').addEventListener('click', function() {
                Array.from(window.parent.document.querySelectorAll('button')).forEach(b => {
                    if (b.innerText.trim() === 'TRIGGER_GOOGLE') b.click();
                });
            });
            const hide = () => {
                Array.from(window.parent.document.querySelectorAll('button')).forEach(b => {
                    if (b.innerText.trim() === 'TRIGGER_GOOGLE') {
                        b.style.setProperty('display', 'none', 'important');
                        b.style.setProperty('visibility', 'hidden', 'important');
                        b.style.setProperty('height', '0', 'important');
                        b.style.setProperty('overflow', 'hidden', 'important');
                        b.style.setProperty('margin', '0', 'important');
                        b.style.setProperty('padding', '0', 'important');
                    }
                });
            };
            [0, 100, 300, 600, 1000, 2000].forEach(t => setTimeout(hide, t));
            </script>
            """,
            height=52,
        )

        if st.button("TRIGGER_GOOGLE", key="google_login_btn", use_container_width=True):
            st.login()
            st.stop()

        if st.button("Back", use_container_width=True, key="login_back_btn"):
            try:
                st.query_params["view"] = "landing"
            except Exception:
                st.experimental_set_query_params(view="landing")
            st.rerun()


# -----------------------------
# Global styles
# -----------------------------
def inject_global_styles():
    st.markdown(
        """
        <style>
        :root {
            --ca-bg-1: #000000;
            --ca-bg-2: #030816;
            --ca-bg-3: #071226;
            --ca-panel: rgba(5, 14, 34, 0.92);
            --ca-panel-2: rgba(8, 20, 46, 0.90);
            --ca-border: rgba(88, 166, 255, 0.16);
            --ca-text: #eef4ff;
            --ca-muted: #9db2d6;
            --ca-blue: #58a6ff;
            --ca-cyan: #7ee8ff;
            --ca-lime: #cfee76;
            --ca-shadow: 0 18px 50px rgba(0,0,0,0.40);
            --ca-danger: #ff6b6b;
            --ca-danger-border: rgba(255, 107, 107, 0.28);
            --ca-danger-bg-1: rgba(45, 10, 10, 0.92);
            --ca-danger-bg-2: rgba(22, 5, 5, 0.96);
        }

        .stApp {
            background:
                radial-gradient(circle at top center, rgba(88,166,255,0.10), transparent 26%),
                radial-gradient(circle at 75% 30%, rgba(126,232,255,0.06), transparent 20%),
                linear-gradient(180deg, var(--ca-bg-1) 0%, var(--ca-bg-2) 45%, var(--ca-bg-3) 100%);
            color: var(--ca-text);
        }

        .block-container {
            padding-top: 1rem;
            padding-bottom: 2rem;
            max-width: 1500px;
        }

        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #000000 0%, #020914 50%, #041125 100%);
            border-right: 1px solid rgba(88, 166, 255, 0.10);
        }

        section[data-testid="stSidebar"] .block-container {
            padding-top: 1rem;
            padding-left: 1rem;
            padding-right: 1rem;
            display: flex;
            flex-direction: column;
            min-height: 100vh;
        }

        .ca-sidebar-brand-wrap {
            text-align: center;
            margin-top: 0.1rem;
            margin-bottom: 1rem;
        }

        .ca-sidebar-logo-full {
            width: 100%;
            max-width: 190px;
            display: block;
            margin: 0 auto;
            object-fit: contain;
            filter: drop-shadow(0 0 18px rgba(126,232,255,0.08));
            border-radius: 18px;
        }

        .ca-login-subtitle {
            color: #adc1e3;
            font-size: 0.98rem;
            line-height: 1.6;
            margin-bottom: 1rem;
        }

        .ca-landing-outer {
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 80vh;
            padding: 2rem 1rem;
        }

        .ca-landing-card {
            width: 100%;
            max-width: 760px;
            text-align: center;
            padding: 2.5rem 1.5rem 1.2rem 1.5rem;
            border-radius: 30px;
            background:
                radial-gradient(circle at center, rgba(126,232,255,0.06), transparent 24%),
                linear-gradient(135deg, rgba(3,10,24,0.98), rgba(6,18,42,0.95));
            border: 1px solid rgba(126,232,255,0.10);
            box-shadow: 0 18px 50px rgba(0,0,0,0.40);
            margin: 0 auto;
        }

        .ca-logo {
            width: 100%;
            max-width: 420px;
            max-height: 420px;
            display: block;
            margin: 0 auto;
            object-fit: contain;
            filter: drop-shadow(0 0 24px rgba(126,232,255,0.08));
        }

        .ca-tagline {
            color: #7ee8ff;
            font-size: 1.08rem;
            font-weight: 700;
            margin-top: 0.35rem;
            margin-bottom: 1.35rem;
        }

        div[role="radiogroup"] > label {
            background: transparent !important;
            border: 1px solid transparent !important;
            border-radius: 14px !important;
            padding: 0.45rem 0.65rem !important;
            margin-bottom: 0.32rem !important;
            transition: all 0.2s ease;
        }

        div[role="radiogroup"] > label:hover {
            background: rgba(88,166,255,0.08) !important;
            border: 1px solid rgba(126,232,255,0.10) !important;
        }

        div[role="radiogroup"] p {
            color: #e2ecff !important;
            font-size: 1rem !important;
            font-weight: 600 !important;
        }

        .caplytix-divider {
            height: 1px;
            background: linear-gradient(90deg, rgba(88,166,255,0.03), rgba(126,232,255,0.20), rgba(207,238,118,0.03));
            margin: 14px 0 18px 0;
        }

        .sidebar-spacer {
            flex: 1 1 auto;
            min-height: 2rem;
        }

        div[data-testid="stMetric"] {
            background: linear-gradient(180deg, rgba(4,12,28,0.94), rgba(8,20,46,0.90));
            border: 1px solid rgba(126,232,255,0.10);
            border-radius: 22px;
            padding: 16px 18px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.25);
            backdrop-filter: blur(8px);
        }

        div[data-testid="stMetricLabel"] {
            color: #b8caea;
            font-weight: 600;
            font-size: 0.95rem;
        }

        div[data-testid="stMetricValue"] {
            color: #eef4ff;
            font-weight: 800;
        }

        div[data-testid="stMetricDelta"] {
            color: #7ee8ff;
        }

        .caplytix-card {
            background: linear-gradient(180deg, rgba(4,12,28,0.94), rgba(8,20,46,0.90));
            border: 1px solid rgba(126,232,255,0.10);
            border-radius: 22px;
            padding: 20px 20px 18px 20px;
            box-shadow: 0 14px 36px rgba(0,0,0,0.24);
            margin-bottom: 1rem;
        }

        .caplytix-card h3 {
            margin: 0 0 8px 0;
            color: #edf4ff;
            font-size: 1.08rem;
            font-weight: 700;
        }

        .caplytix-card p {
            margin: 0;
            color: #adc1e3;
            line-height: 1.58;
            font-size: 0.96rem;
        }

        .caplytix-kicker {
            color: #7ee8ff;
            text-transform: uppercase;
            letter-spacing: 0.10em;
            font-size: 0.74rem;
            font-weight: 800;
            margin-bottom: 8px;
        }

        /* Default buttons */
        .stButton > button {
            border-radius: 14px !important;
            border: 1px solid rgba(126,232,255,0.14) !important;
            background: linear-gradient(180deg, rgba(10,24,50,0.95), rgba(4,12,28,0.95)) !important;
            color: #eef4ff !important;
            font-weight: 700 !important;
            box-shadow: 0 8px 20px rgba(0,0,0,0.22);
        }

        .stButton > button:hover {
            border-color: rgba(126,232,255,0.25) !important;
            box-shadow: 0 0 0 1px rgba(126,232,255,0.05), 0 10px 24px rgba(0,0,0,0.28);
        }

        /* ENTER THE ARENA button */
        div[data-testid="stMainBlockContainer"] .stButton > button {
            background: linear-gradient(135deg, rgba(3,10,24,0.98), rgba(6,18,42,0.95)) !important;
            border: 1px solid rgba(126,232,255,0.28) !important;
            border-radius: 14px !important;
            color: #cfee76 !important;
            font-size: 1.05rem !important;
            font-weight: 900 !important;
            letter-spacing: 0.12em !important;
            text-transform: uppercase !important;
            text-shadow: 0 0 14px rgba(207,238,118,0.30) !important;
            box-shadow: 0 0 18px rgba(126,232,255,0.08), 0 8px 24px rgba(0,0,0,0.30) !important;
            transition: all 0.2s ease !important;
            padding: 0.65rem 1rem !important;
        }

        div[data-testid="stMainBlockContainer"] .stButton > button:hover {
            border-color: rgba(207,238,118,0.40) !important;
            color: #e6ffad !important;
            text-shadow: 0 0 20px rgba(207,238,118,0.50) !important;
            box-shadow: 0 0 28px rgba(207,238,118,0.12), 0 10px 30px rgba(0,0,0,0.35) !important;
        }

        /* Logout button red */
        section[data-testid="stSidebar"] .stButton:last-of-type > button {
            color: #ff6b6b !important;
            border-color: rgba(255, 107, 107, 0.20) !important;
        }

        section[data-testid="stSidebar"] .stButton:last-of-type > button:hover {
            color: #ff8787 !important;
            border-color: rgba(255, 107, 107, 0.40) !important;
            box-shadow: 0 0 18px rgba(255,107,107,0.10) !important;
        }

        @media (max-width: 900px) {
            .ca-logo {
                max-width: 320px;
                max-height: 320px;
            }
            .ca-sidebar-logo-full {
                max-width: 160px;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_section_card(title: str, body: str, kicker: str = ""):
    kicker_html = f'<div class="caplytix-kicker">{kicker}</div>' if kicker else ""
    st.markdown(
        f"""
        <div class="caplytix-card">
            {kicker_html}
            <h3>{title}</h3>
            <p>{body}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# -----------------------------
# Data helpers
# -----------------------------
def get_all_daily_raw(user_email: str) -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query(
        """
        SELECT trade_date, deposit, withdrawal, daily_pnl
        FROM daily_performance
        WHERE user_email = ?
        ORDER BY trade_date ASC
        """,
        conn,
        params=(user_email,),
    )
    if df.empty:
        return pd.DataFrame(columns=["trade_date", "deposit", "withdrawal", "daily_pnl"])
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    for col in ["deposit", "withdrawal", "daily_pnl"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df


def compute_daily_metrics(raw_df: pd.DataFrame, starting_balance: float) -> pd.DataFrame:
    cols = [
        "Date", "Trading Day Number", "Balance Before Trading",
        "Deposit", "Withdrawal", "Daily P&L ($)", "Daily %",
        "Ending Balance", "Next Day Target Balance",
    ]
    if raw_df is None or raw_df.empty:
        return pd.DataFrame(columns=cols)

    df = raw_df.copy().sort_values("trade_date").reset_index(drop=True)
    records = []
    prior_ending = float(starting_balance)
    cumulative_daily_pcts = []

    for i, row in df.iterrows():
        balance_before = prior_ending
        daily_pnl = float(row["daily_pnl"])
        deposit = float(row["deposit"])
        withdrawal = float(row["withdrawal"])
        daily_pct = (daily_pnl / balance_before) if balance_before != 0 else 0.0
        ending_balance = balance_before + daily_pnl + deposit - withdrawal
        cumulative_daily_pcts.append(daily_pct)
        avg_pct_so_far = float(np.mean(cumulative_daily_pcts))
        next_day_target = ending_balance * (1 + avg_pct_so_far)

        records.append({
            "Date": pd.to_datetime(row["trade_date"]).date(),
            "Trading Day Number": i + 1,
            "Balance Before Trading": balance_before,
            "Deposit": deposit,
            "Withdrawal": withdrawal,
            "Daily P&L ($)": daily_pnl,
            "Daily %": daily_pct,
            "Ending Balance": ending_balance,
            "Next Day Target Balance": next_day_target,
        })
        prior_ending = ending_balance

    return pd.DataFrame(records)


def get_daily_metrics(user_email: str) -> pd.DataFrame:
    settings = load_settings(user_email)
    raw_df = get_all_daily_raw(user_email)
    return compute_daily_metrics(raw_df, settings["starting_balance"])


def upsert_daily_entry(user_email: str, trade_date: date, deposit: float, withdrawal: float, daily_pnl: float):
    conn = get_conn()
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO daily_performance (trade_date, user_email, deposit, withdrawal, daily_pnl, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(trade_date, user_email) DO UPDATE SET
            deposit = excluded.deposit,
            withdrawal = excluded.withdrawal,
            daily_pnl = excluded.daily_pnl,
            updated_at = excluded.updated_at
        """,
        (trade_date.isoformat(), user_email, deposit, withdrawal, daily_pnl, now, now),
    )
    conn.commit()


def delete_daily_entry(user_email: str, trade_date: date):
    conn = get_conn()
    conn.execute(
        "DELETE FROM daily_performance WHERE trade_date = ? AND user_email = ?",
        (trade_date.isoformat(), user_email),
    )
    conn.commit()


def get_all_trades(user_email: str) -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query(
        "SELECT * FROM trade_journal WHERE user_email = ? ORDER BY trade_date ASC, id ASC",
        conn,
        params=(user_email,),
    )
    if df.empty:
        return pd.DataFrame(columns=[
            "id", "trade_date", "ticker", "trade_type", "direction", "quantity",
            "entry_price", "exit_price", "option_side", "strike", "expiration_date",
            "mistake_categories", "mistake_tags", "edge_categories", "edge_tags",
            "discipline_score", "notes",
        ])
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    df["expiration_date"] = pd.to_datetime(df["expiration_date"], errors="coerce").dt.date
    for col in ["mistake_categories", "mistake_tags", "edge_categories", "edge_tags"]:
        df[col] = df[col].apply(json_loads_list)
    return df


def discipline_score_from_tags(mistake_tags: List[str], edge_tags: List[str]) -> float:
    mistake_lookup = {tag: w for _, tags in MISTAKE_TAGS_BY_CATEGORY.items() for tag, w in tags.items()}
    edge_lookup = {tag: w for _, tags in EDGE_TAGS_BY_CATEGORY.items() for tag, w in tags.items()}
    penalty = sum(mistake_lookup.get(tag, 0) for tag in mistake_tags)
    bonus = sum(edge_lookup.get(tag, 0) for tag in edge_tags)
    return round(clamp(100 - penalty + bonus, 0, 100), 2)


def upsert_trade(user_email, trade_id, trade_date, ticker, trade_type, direction,
                 quantity, entry_price, exit_price, option_side, strike,
                 expiration_date, mistake_categories, mistake_tags,
                 edge_categories, edge_tags, notes):
    conn = get_conn()
    now = datetime.now().isoformat(timespec="seconds")
    score = discipline_score_from_tags(mistake_tags, edge_tags)

    payload = (
        user_email,
        trade_date.isoformat(),
        ticker.upper().strip(),
        trade_type,
        direction,
        float(quantity or 0),
        float(entry_price or 0),
        float(exit_price or 0),
        option_side if trade_type == "Options" else None,
        float(strike) if (trade_type == "Options" and strike not in [None, ""]) else None,
        expiration_date.isoformat() if (trade_type == "Options" and expiration_date) else None,
        json_dumps_list(mistake_categories),
        json_dumps_list(mistake_tags),
        json_dumps_list(edge_categories),
        json_dumps_list(edge_tags),
        float(score),
        notes or "",
        now,
    )

    if trade_id is None:
        conn.execute(
            """
            INSERT INTO trade_journal (
                user_email, trade_date, ticker, trade_type, direction, quantity,
                entry_price, exit_price, option_side, strike, expiration_date,
                mistake_categories, mistake_tags, edge_categories, edge_tags,
                discipline_score, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            payload + (now,),
        )
    else:
        conn.execute(
            """
            UPDATE trade_journal SET
                user_email=?, trade_date=?, ticker=?, trade_type=?, direction=?,
                quantity=?, entry_price=?, exit_price=?, option_side=?, strike=?,
                expiration_date=?, mistake_categories=?, mistake_tags=?,
                edge_categories=?, edge_tags=?, discipline_score=?, notes=?, updated_at=?
            WHERE id=? AND user_email=?
            """,
            payload + (trade_id, user_email),
        )
    conn.commit()
    return score


def delete_trade(user_email: str, trade_id: int):
    conn = get_conn()
    conn.execute(
        "DELETE FROM trade_journal WHERE id = ? AND user_email = ?",
        (trade_id, user_email),
    )
    conn.commit()


# -----------------------------
# Chart + analytics helpers
# -----------------------------
def build_projection_chart(daily_df: pd.DataFrame, starting_balance: float, tracking_days: int, height: int = 320):
    tracking_days = max(int(tracking_days), 1)

    if daily_df.empty:
        avg_daily_pct = 0.0
        actual_points = [{"Day": 0, "Balance": starting_balance, "Series": "Actual"}]
        latest_ending = starting_balance
    else:
        avg_daily_pct = float(daily_df["Daily %"].mean())
        actual_points = [{"Day": 0, "Balance": starting_balance, "Series": "Actual"}]
        for _, row in daily_df.iterrows():
            actual_points.append({
                "Day": int(row["Trading Day Number"]),
                "Balance": float(row["Ending Balance"]),
                "Series": "Actual",
            })
        latest_ending = float(daily_df["Ending Balance"].iloc[-1])

    projected_points = []
    projected_balance = float(starting_balance)
    for day_num in range(0, tracking_days + 1):
        if day_num == 0:
            projected_balance = float(starting_balance)
        else:
            projected_balance = projected_balance * (1 + avg_daily_pct)
        projected_points.append({"Day": day_num, "Balance": projected_balance, "Series": "Projected"})

    chart_df = pd.DataFrame(projected_points + actual_points)
    color_scale = alt.Scale(domain=["Projected", "Actual"], range=["#2563eb", "#dc2626"])

    chart = (
        alt.Chart(chart_df)
        .mark_line(strokeWidth=3)
        .encode(
            x=alt.X("Day:Q", title="Day"),
            y=alt.Y("Balance:Q", title="Balance"),
            color=alt.Color("Series:N", scale=color_scale, title=""),
            tooltip=[
                alt.Tooltip("Series:N"),
                alt.Tooltip("Day:Q"),
                alt.Tooltip("Balance:Q", format=",.2f"),
            ],
        )
        .properties(height=height)
    )
    return chart, latest_ending, avg_daily_pct


def get_dashboard_metrics(daily_df: pd.DataFrame, settings: Dict[str, object]) -> Dict[str, float]:
    starting_balance = float(settings["starting_balance"])
    tracking_days = int(settings["tracking_days"])
    trading_days_completed = len(daily_df)
    trading_days_left = max(tracking_days - trading_days_completed, 0)

    if daily_df.empty:
        current_balance = starting_balance
        avg_daily_pct = 0.0
        next_day_target = starting_balance
        projected_end_balance = starting_balance
        net_deposits = 0.0
    else:
        current_balance = float(daily_df["Ending Balance"].iloc[-1])
        avg_daily_pct = float(daily_df["Daily %"].mean())
        next_day_target = current_balance * (1 + avg_daily_pct)
        projected_end_balance = current_balance * ((1 + avg_daily_pct) ** trading_days_left)
        net_deposits = float(daily_df["Deposit"].sum() - daily_df["Withdrawal"].sum())

    actual_growth_dollars = current_balance - starting_balance
    actual_growth_pct = actual_growth_dollars / starting_balance if starting_balance else 0.0
    trade_only_growth_dollars = current_balance - starting_balance - net_deposits
    trade_only_growth_pct = trade_only_growth_dollars / starting_balance if starting_balance else 0.0

    return {
        "current_balance": current_balance,
        "avg_daily_pct": avg_daily_pct,
        "projected_end_balance": projected_end_balance,
        "next_day_target": next_day_target,
        "trading_days_completed": trading_days_completed,
        "trading_days_left": trading_days_left,
        "actual_growth_dollars": actual_growth_dollars,
        "actual_growth_pct": actual_growth_pct,
        "trade_only_growth_dollars": trade_only_growth_dollars,
        "trade_only_growth_pct": trade_only_growth_pct,
    }


def get_top_tag_counts(trades_df: pd.DataFrame):
    if trades_df.empty:
        return [], []
    all_mistakes = [tag for tags in trades_df["mistake_tags"] for tag in tags]
    all_edges = [tag for tags in trades_df["edge_tags"] for tag in tags]
    top_mistakes = pd.Series(all_mistakes).value_counts().head(4).to_dict() if all_mistakes else {}
    top_edges = pd.Series(all_edges).value_counts().head(4).to_dict() if all_edges else {}
    return list(top_mistakes.items()), list(top_edges.items())


def get_ai_scorecard(daily_df: pd.DataFrame, trades_df: pd.DataFrame):
    scorecard = {
        "Performance Score": 50,
        "Discipline Score": 50,
        "Consistency Score": 50,
        "Process Score": 50,
    }
    if not daily_df.empty:
        avg_pct = float(daily_df["Daily %"].mean())
        win_rate = float((daily_df["Daily P&L ($)"] > 0).mean())
        pnl_std = float(daily_df["Daily P&L ($)"].std()) if len(daily_df) > 1 else 0.0
        avg_abs_pnl = float(daily_df["Daily P&L ($)"].abs().mean())
        perf_score = 50 + (avg_pct * 1200) + ((win_rate - 0.5) * 40)
        consistency_score = 72 if (avg_abs_pnl > 0 and pnl_std <= avg_abs_pnl) else 52
        if len(daily_df) < 5:
            consistency_score -= 8
        scorecard["Performance Score"] = int(clamp(perf_score, 0, 100))
        scorecard["Consistency Score"] = int(clamp(consistency_score, 0, 100))
    if not trades_df.empty:
        avg_discipline = float(trades_df["discipline_score"].mean())
        low_discipline_pct = float((trades_df["discipline_score"] < 70).mean())
        tagged_ratio = float(
            (trades_df["mistake_tags"].apply(len) + trades_df["edge_tags"].apply(len)).gt(0).mean()
        )
        process_score = 55 + (tagged_ratio * 30) - (low_discipline_pct * 25)
        scorecard["Discipline Score"] = int(clamp(avg_discipline, 0, 100))
        scorecard["Process Score"] = int(clamp(process_score, 0, 100))
    return scorecard


def get_focus_message(scorecard: dict) -> str:
    weakest = min(scorecard, key=scorecard.get)
    mapping = {
        "Performance Score": "Your biggest focus right now is translating your process into stronger net performance.",
        "Discipline Score": "Your biggest focus right now is behavioral discipline before, during, and after execution.",
        "Consistency Score": "Your biggest focus right now is smoothing out volatility and making your daily outcomes more repeatable.",
        "Process Score": "Your biggest focus right now is tightening preparation, tagging, and structured review habits.",
    }
    return mapping.get(weakest, "Your biggest focus right now is tightening execution and process consistency.")


def dashboard_ai_summary(daily_df, trades_df, metrics):
    if daily_df.empty and trades_df.empty:
        return "No trading data yet. Start with Daily Performance for balance tracking, then use Trade Journal for behavioral review."
    parts = []
    avg_pct = metrics["avg_daily_pct"]
    if avg_pct > 0.01:
        parts.append("Your daily average is strong and currently compounding in a healthy direction.")
    elif avg_pct > 0:
        parts.append("You are positive on average, but the edge is still modest and needs consistency.")
    elif avg_pct == 0:
        parts.append("Your account is flat so far, so the biggest opportunity is consistency and sample size.")
    else:
        parts.append("Your current average daily return is negative, so tightening execution and risk control should be the immediate priority.")
    if not trades_df.empty:
        avg_discipline = float(trades_df["discipline_score"].mean())
        if avg_discipline >= 85:
            parts.append("Discipline scores are strong, which suggests your process is supporting your results.")
        elif avg_discipline >= 70:
            parts.append("Discipline is decent, but there are still enough process leaks to improve.")
        else:
            parts.append("Behavioral discipline is weak relative to your goals and may be dragging consistency.")
    if not daily_df.empty:
        pnl_std = float(daily_df["Daily P&L ($)"].std()) if len(daily_df) > 1 else 0.0
        avg_abs_pnl = float(daily_df["Daily P&L ($)"].abs().mean())
        if avg_abs_pnl > 0 and pnl_std > avg_abs_pnl:
            parts.append("Your P&L swings are wider than your typical day, which points to uneven execution or sizing.")
        else:
            parts.append("Your recent balance path is relatively stable compared with your average day.")
    return " ".join(parts)


def psychology_review(daily_df, trades_df):
    empty_msg = "Not enough data yet. Add Daily Performance entries and Trade Journal notes to generate a tailored review."
    if daily_df.empty and trades_df.empty:
        return {k: empty_msg for k in ["Trading Style Profile", "Strengths", "Weaknesses", "Pattern Breakdown", "Coaching Actions", "Tailored Summary"]}

    style_bits, strengths, weaknesses, patterns, actions, summary = [], [], [], [], [], []

    if not daily_df.empty:
        avg_pct = float(daily_df["Daily %"].mean())
        win_rate = float((daily_df["Daily P&L ($)"] > 0).mean())
        pnl_std = float(daily_df["Daily P&L ($)"].std()) if len(daily_df) > 1 else 0.0
        avg_abs_pnl = float(daily_df["Daily P&L ($)"].abs().mean())

        if avg_pct > 0 and win_rate >= 0.5:
            style_bits.append("Your results suggest a productive, growth-oriented trading approach.")
            strengths.append("You are producing a positive average return with enough green days to support confidence.")
        elif avg_pct > 0:
            style_bits.append("You appear selective enough to stay net positive, even with mixed day-to-day consistency.")
            strengths.append("Your edge is positive overall, which means the base strategy has potential.")
        else:
            style_bits.append("Your recent results suggest a reactive profile that still needs tighter structure.")
            weaknesses.append("Your current daily result profile is not yet supporting positive compounding.")

        if pnl_std > avg_abs_pnl and avg_abs_pnl > 0:
            weaknesses.append("Your daily swings are larger than your typical result, pointing to unstable execution or sizing.")
            actions.append("Reduce size on non-A+ setups and define one max-loss rule you do not break.")
            patterns.append("Large variation in daily outcomes suggests that risk expression changes too much from day to day.")
        else:
            strengths.append("Your balance path is relatively controlled compared with your typical day.")
            patterns.append("The account curve shows a steadier rhythm than a high-chaos trading pattern.")

    if not trades_df.empty:
        avg_discipline = float(trades_df["discipline_score"].mean())
        low_discipline_pct = float((trades_df["discipline_score"] < 70).mean())
        all_mistakes = [tag for tags in trades_df["mistake_tags"] for tag in tags]
        all_edges = [tag for tags in trades_df["edge_tags"] for tag in tags]
        top_mistakes = pd.Series(all_mistakes).value_counts().head(3) if all_mistakes else pd.Series(dtype=int)
        top_edges = pd.Series(all_edges).value_counts().head(3) if all_edges else pd.Series(dtype=int)

        if avg_discipline >= 85:
            strengths.append("Your average discipline score is strong.")
        elif avg_discipline >= 70:
            summary.append("Your discipline is workable, but not yet reliable enough to trust on autopilot.")
        else:
            weaknesses.append("Your average discipline score is low enough that process is likely hurting performance.")
            actions.append("Before every trade, force a 15-second checklist: setup, invalidation, size, and exit plan.")

        if low_discipline_pct > 0.3:
            patterns.append("A meaningful chunk of your journaled trades fall below a strong discipline threshold.")
            actions.append("Review only the lowest-discipline trades first. Fix the repeated behavior before anything else.")

        if not top_mistakes.empty:
            mistake_text = ", ".join([f"{idx} ({val})" for idx, val in top_mistakes.items()])
            weaknesses.append(f"Most common mistake patterns: {mistake_text}.")
        if not top_edges.empty:
            edge_text = ", ".join([f"{idx} ({val})" for idx, val in top_edges.items()])
            strengths.append(f"Your best repeated edge behaviors: {edge_text}.")
            actions.append("Build your next week around repeating the edge tags that already show up in your best journal entries.")

        notes_text = " ".join([str(x) for x in trades_df["notes"].fillna("").tolist()]).lower()
        if any(w in notes_text for w in ["fomo", "chase", "late"]):
            weaknesses.append("Your notes suggest reactive entries may be showing up during fast moves.")
        if any(w in notes_text for w in ["patient", "plan", "waited"]):
            strengths.append("Your notes show you already know how patience improves execution.")

    if not strengths:
        strengths.append("You are building a trackable process, which is the foundation for real improvement.")
    if not weaknesses:
        weaknesses.append("No dominant weakness stands out yet, but more sample size will sharpen the review.")
    if not patterns:
        patterns.append("More trades and daily entries will make recurring behavior easier to identify.")
    if not actions:
        actions.append("Keep journaling every trade and review the last 5 entries before the next session.")
    if not summary:
        summary.append("Your data suggests the biggest gains will come from repeating your best behaviors more consistently.")

    return {
        "Trading Style Profile": " ".join(style_bits) if style_bits else "Your trading style is still forming.",
        "Strengths": " ".join(strengths),
        "Weaknesses": " ".join(weaknesses),
        "Pattern Breakdown": " ".join(patterns),
        "Coaching Actions": " ".join(actions),
        "Tailored Summary": " ".join(summary),
    }


def show_weight_tables():
    st.subheader("Mistake Tag Weights")
    mistake_rows = [{"Category": cat, "Tag": tag, "Weight": w} for cat, tags in MISTAKE_TAGS_BY_CATEGORY.items() for tag, w in tags.items()]
    st.dataframe(pd.DataFrame(mistake_rows), use_container_width=True, hide_index=True)
    st.subheader("Edge Tag Weights")
    edge_rows = [{"Category": cat, "Tag": tag, "Weight": w} for cat, tags in EDGE_TAGS_BY_CATEGORY.items() for tag, w in tags.items()]
    st.dataframe(pd.DataFrame(edge_rows), use_container_width=True, hide_index=True)


# -----------------------------
# Session state
# -----------------------------
def ensure_state():
    defaults = {
        "daily_open_section": None,
        "trade_open_section": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# -----------------------------
# Pages
# -----------------------------
def page_dashboard(user_email: str):
    settings = load_settings(user_email)
    daily_df = get_daily_metrics(user_email)
    trades_df = get_all_trades(user_email)
    metrics = get_dashboard_metrics(daily_df, settings)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Current Balance", fmt_money(metrics["current_balance"]))
    c2.metric("Average Daily %", fmt_pct(metrics["avg_daily_pct"]))
    c3.metric("Projected End Balance", fmt_money(metrics["projected_end_balance"]))
    c4.metric("Next Day Target Balance", fmt_money(metrics["next_day_target"]))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Trading Days Completed", f'{metrics["trading_days_completed"]:,}')
    c6.metric("Trading Days Left", f'{metrics["trading_days_left"]:,}')
    c7.metric("Actual Growth (w/ deposits)", fmt_money(metrics["actual_growth_dollars"]), delta=fmt_pct(metrics["actual_growth_pct"]))
    c8.metric("Trade-Only Growth (w/o deposits)", fmt_money(metrics["trade_only_growth_dollars"]), delta=fmt_pct(metrics["trade_only_growth_pct"]))

    st.markdown('<div class="caplytix-divider"></div>', unsafe_allow_html=True)

    left, right = st.columns([1.7, 1])
    with left:
        render_section_card("Growth Snapshot", "Blue shows the compounding projection. Red shows your real account path.", kicker="Chart")
        chart, _, _ = build_projection_chart(daily_df, float(settings["starting_balance"]), int(settings["tracking_days"]), height=280)
        st.altair_chart(chart, use_container_width=True)

    with right:
        render_section_card("AI Summary", dashboard_ai_summary(daily_df, trades_df, metrics), kicker="Behavior + Performance")
        scorecard = get_ai_scorecard(daily_df, trades_df)
        s1, s2 = st.columns(2)
        s1.metric("Performance Score", f"{scorecard['Performance Score']}/100")
        s2.metric("Discipline Score", f"{scorecard['Discipline Score']}/100")
        s3, s4 = st.columns(2)
        s3.metric("Consistency Score", f"{scorecard['Consistency Score']}/100")
        s4.metric("Process Score", f"{scorecard['Process Score']}/100")

    st.markdown('<div class="caplytix-divider"></div>', unsafe_allow_html=True)

    bottom_left, bottom_right = st.columns(2)
    with bottom_left:
        if daily_df.empty:
            render_section_card("Last Performance Snapshot", "No Daily Performance entries yet.", kicker="Latest Day")
        else:
            last_row = daily_df.iloc[-1]
            body = (f"Last saved day: {last_row['Date']}. Ending balance: {fmt_money(last_row['Ending Balance'])}. "
                    f"Daily result: {fmt_money(last_row['Daily P&L ($)'])} ({fmt_pct(last_row['Daily %'])}). "
                    f"Next day target: {fmt_money(last_row['Next Day Target Balance'])}.")
            render_section_card("Last Performance Snapshot", body, kicker="Latest Day")

    with bottom_right:
        if trades_df.empty:
            render_section_card("Behavior Snapshot", "No Trade Journal entries yet.", kicker="Journal Context")
        else:
            top_mistakes, top_edges = get_top_tag_counts(trades_df)
            avg_discipline = float(trades_df["discipline_score"].mean())
            top_mistake_text = ", ".join([f"{tag} ({count})" for tag, count in top_mistakes]) if top_mistakes else "None yet"
            top_edge_text = ", ".join([f"{tag} ({count})" for tag, count in top_edges]) if top_edges else "None yet"
            body = f"Average discipline score: {avg_discipline:.2f}. Top mistakes: {top_mistake_text}. Top edges: {top_edge_text}."
            render_section_card("Behavior Snapshot", body, kicker="Journal Context")


def page_daily_performance(user_email: str):
    st.title("Daily Performance")
    st.caption("This is the only page that affects account balances and projections.")

    settings = load_settings(user_email)
    raw_df = get_all_daily_raw(user_email)
    existing_dates = sorted(raw_df["trade_date"].tolist()) if not raw_df.empty else []

    top_left, top_right, top_spacer = st.columns([1, 1, 3])
    if top_left.button("New Entry", use_container_width=True, key="dp_open_new_btn"):
        st.session_state["daily_open_section"] = "new"
    if top_right.button("Edit Previous Entry", use_container_width=True, key="dp_open_edit_btn"):
        st.session_state["daily_open_section"] = "edit"

    open_section = st.session_state.get("daily_open_section")

    if open_section == "new":
        panel = st.container(border=True)
        with panel:
            hdr1, hdr2 = st.columns([4, 1])
            hdr1.subheader("New Entry")
            if hdr2.button("Close", key="dp_close_new"):
                st.session_state["daily_open_section"] = None
                st.rerun()

            entry_date = st.date_input("Date", value=date.today(), key="dp_new_date")
            row1, row2, row3 = st.columns(3)
            deposit = row1.number_input("Deposit", min_value=0.0, value=0.0, step=1.0, key="dp_new_deposit")
            withdrawal = row2.number_input("Withdrawal", min_value=0.0, value=0.0, step=1.0, key="dp_new_withdrawal")
            daily_pnl = row3.number_input("Daily P&L ($)", value=0.0, step=1.0, key="dp_new_pnl")

            preview_raw = pd.concat([raw_df, pd.DataFrame([{"trade_date": entry_date, "deposit": deposit, "withdrawal": withdrawal, "daily_pnl": daily_pnl}])], ignore_index=True)
            preview_metrics = compute_daily_metrics(preview_raw, settings["starting_balance"])
            preview_row = preview_metrics[preview_metrics["Date"] == entry_date].iloc[0]

            st.markdown("#### Preview")
            p1, p2, p3, p4 = st.columns(4)
            p1.metric("Balance Before Trading", f"${preview_row['Balance Before Trading']:,.2f}")
            p2.metric("Daily %", f"{preview_row['Daily %'] * 100:.2f}%")
            p3.metric("Ending Balance", f"${preview_row['Ending Balance']:,.2f}")
            p4.metric("Next Day Target Balance", f"${preview_row['Next Day Target Balance']:,.2f}")

            a1, a2 = st.columns(2)
            if a1.button("Save New Entry", type="primary", key="save_new_entry", use_container_width=True):
                if entry_date in existing_dates:
                    st.error("A Daily Performance entry already exists for that date.")
                else:
                    upsert_daily_entry(user_email, entry_date, deposit, withdrawal, daily_pnl)
                    st.success("Saved successfully.")
                    st.session_state["daily_open_section"] = None
                    st.rerun()
            if a2.button("Cancel", key="cancel_new_entry", use_container_width=True):
                st.session_state["daily_open_section"] = None
                st.rerun()

    elif open_section == "edit":
        panel = st.container(border=True)
        with panel:
            hdr1, hdr2 = st.columns([4, 1])
            hdr1.subheader("Edit Previous Entry")
            if hdr2.button("Close", key="dp_close_edit"):
                st.session_state["daily_open_section"] = None
                st.rerun()

            if not existing_dates:
                st.warning("No saved days yet.")
                return

            selected_date = st.selectbox("Select saved day", options=existing_dates, format_func=lambda x: x.strftime("%Y-%m-%d"), key="dp_edit_select_date")
            match = raw_df[raw_df["trade_date"] == selected_date].iloc[0]

            row1, row2, row3 = st.columns(3)
            deposit = row1.number_input("Deposit", min_value=0.0, value=float(match["deposit"]), step=1.0, key="dp_edit_deposit")
            withdrawal = row2.number_input("Withdrawal", min_value=0.0, value=float(match["withdrawal"]), step=1.0, key="dp_edit_withdrawal")
            daily_pnl = row3.number_input("Daily P&L ($)", value=float(match["daily_pnl"]), step=1.0, key="dp_edit_pnl")

            preview_raw = pd.concat([raw_df[raw_df["trade_date"] != selected_date], pd.DataFrame([{"trade_date": selected_date, "deposit": deposit, "withdrawal": withdrawal, "daily_pnl": daily_pnl}])], ignore_index=True)
            preview_metrics = compute_daily_metrics(preview_raw, settings["starting_balance"])
            preview_row = preview_metrics[preview_metrics["Date"] == selected_date].iloc[0]

            st.markdown("#### Preview")
            p1, p2, p3, p4 = st.columns(4)
            p1.metric("Balance Before Trading", f"${preview_row['Balance Before Trading']:,.2f}")
            p2.metric("Daily %", f"{preview_row['Daily %'] * 100:.2f}%")
            p3.metric("Ending Balance", f"${preview_row['Ending Balance']:,.2f}")
            p4.metric("Next Day Target Balance", f"${preview_row['Next Day Target Balance']:,.2f}")

            a1, a2, a3 = st.columns(3)
            if a1.button("Save Changes", type="primary", key="save_edit_entry", use_container_width=True):
                upsert_daily_entry(user_email, selected_date, deposit, withdrawal, daily_pnl)
                st.success("Saved successfully.")
                st.session_state["daily_open_section"] = None
                st.rerun()
            if a2.button("Delete Day", key="delete_edit_entry", use_container_width=True):
                delete_daily_entry(user_email, selected_date)
                st.success("Entry deleted.")
                st.session_state["daily_open_section"] = None
                st.rerun()
            if a3.button("Cancel", key="cancel_edit_entry", use_container_width=True):
                st.session_state["daily_open_section"] = None
                st.rerun()
    else:
        st.info("Choose New Entry or Edit Previous Entry to open the form.")


def page_performance_history(user_email: str):
    st.title("Performance History")
    daily_df = get_daily_metrics(user_email)

    if daily_df.empty:
        st.info("No Daily Performance data yet.")
        return

    min_date = daily_df["Date"].min()
    max_date = daily_df["Date"].max()

    c1, c2 = st.columns(2)
    start_date = c1.date_input("Start date", value=min_date, min_value=min_date, max_value=max_date)
    end_date = c2.date_input("End date", value=max_date, min_value=min_date, max_value=max_date)

    filtered = daily_df[(daily_df["Date"] >= start_date) & (daily_df["Date"] <= end_date)].copy()

    q1, q2, q3, q4, q5 = st.columns(5)
    q1.metric("Total Days in Range", f"{len(filtered):,}")
    q2.metric("Total P&L ($)", fmt_money(filtered["Daily P&L ($)"].sum()))
    q3.metric("Average Daily %", fmt_pct(filtered["Daily %"].mean() if len(filtered) else 0))
    q4.metric("Best Day ($)", fmt_money(filtered["Daily P&L ($)"].max() if len(filtered) else 0))
    q5.metric("Worst Day ($)", fmt_money(filtered["Daily P&L ($)"].min() if len(filtered) else 0))

    st.dataframe(
        filtered, use_container_width=True, hide_index=True,
        column_config={
            "Date": st.column_config.DateColumn("Date"),
            "Trading Day Number": st.column_config.NumberColumn("Trading Day Number", format="%d"),
            "Balance Before Trading": st.column_config.NumberColumn("Balance Before Trading", format="$%.2f"),
            "Deposit": st.column_config.NumberColumn("Deposit", format="$%.2f"),
            "Withdrawal": st.column_config.NumberColumn("Withdrawal", format="$%.2f"),
            "Daily P&L ($)": st.column_config.NumberColumn("Daily P&L ($)", format="$%.2f"),
            "Daily %": st.column_config.NumberColumn("Daily %", format="%.2f%%"),
            "Ending Balance": st.column_config.NumberColumn("Ending Balance", format="$%.2f"),
            "Next Day Target Balance": st.column_config.NumberColumn("Next Day Target Balance", format="$%.2f"),
        },
    )


def page_trade_journal(user_email: str):
    st.title("Trade Journal")
    st.caption("Behavioral journaling only. This page does not affect Daily Performance or Performance History.")

    trades_df = get_all_trades(user_email)

    top_left, top_right, top_spacer = st.columns([1, 1, 3])
    if top_left.button("New Entry", use_container_width=True, key="tj_open_new_btn"):
        st.session_state["trade_open_section"] = "new"
    if top_right.button("Edit Previous Entry", use_container_width=True, key="tj_open_edit_btn"):
        st.session_state["trade_open_section"] = "edit"

    open_section = st.session_state.get("trade_open_section")

    if open_section == "new":
        panel = st.container(border=True)
        with panel:
            hdr1, hdr2 = st.columns([4, 1])
            hdr1.subheader("New Entry")
            if hdr2.button("Close", key="tj_close_new"):
                st.session_state["trade_open_section"] = None
                st.rerun()

            row1 = st.columns(4)
            trade_date = row1[0].date_input("Date", value=date.today(), key="tj_date_new")
            ticker = row1[1].text_input("Ticker", value="", key="tj_ticker_new")
            trade_type = row1[2].selectbox("Trade Type", TRADE_TYPES, key="tj_type_new")
            direction = row1[3].selectbox("Direction", DIRECTIONS, key="tj_direction_new")

            row2 = st.columns(3)
            quantity = row2[0].number_input("Quantity", min_value=0.0, value=1.0, step=1.0, key="tj_qty_new")
            entry_price = row2[1].number_input("Entry Price", min_value=0.0, value=0.0, step=0.01, key="tj_entry_new")
            exit_price = row2[2].number_input("Exit Price", min_value=0.0, value=0.0, step=0.01, key="tj_exit_new")

            option_side = strike = expiration_date = None
            if trade_type == "Options":
                row3 = st.columns(3)
                option_side = row3[0].selectbox("Option Side", OPTION_SIDES, key="tj_opt_side_new")
                strike = row3[1].number_input("Strike", min_value=0.0, value=0.0, step=0.5, key="tj_strike_new")
                expiration_date = row3[2].date_input("Expiration Date", value=date.today(), key="tj_exp_new")

            tag_col1, tag_col2 = st.columns(2)
            with tag_col1:
                mistake_categories = st.multiselect("Mistake Categories", list(MISTAKE_TAGS_BY_CATEGORY.keys()), key="tj_mcat_new")
                available_mistake_tags = sorted({tag for cat in mistake_categories for tag in MISTAKE_TAGS_BY_CATEGORY.get(cat, {}).keys()})
                mistake_tags = st.multiselect("Mistake Tags", available_mistake_tags, key="tj_mtags_new")
            with tag_col2:
                edge_categories = st.multiselect("Edge Categories", list(EDGE_TAGS_BY_CATEGORY.keys()), key="tj_ecat_new")
                available_edge_tags = sorted({tag for cat in edge_categories for tag in EDGE_TAGS_BY_CATEGORY.get(cat, {}).keys()})
                edge_tags = st.multiselect("Edge Tags", available_edge_tags, key="tj_etags_new")

            notes = st.text_area("Notes", value="", key="tj_notes_new", height=140)
            score = discipline_score_from_tags(mistake_tags, edge_tags)
            st.metric("Auto Discipline Score", f"{score:.2f}")

            a1, a2 = st.columns(2)
            if a1.button("Save Trade", type="primary", key="save_trade_new", use_container_width=True):
                if not ticker.strip():
                    st.error("Ticker is required.")
                else:
                    saved_score = upsert_trade(user_email, None, trade_date, ticker, trade_type, direction,
                                               quantity, entry_price, exit_price, option_side, strike,
                                               expiration_date, mistake_categories, mistake_tags,
                                               edge_categories, edge_tags, notes)
                    st.success(f"Trade saved. Discipline Score: {saved_score:.2f}")
                    st.session_state["trade_open_section"] = None
                    st.rerun()
            if a2.button("Cancel", key="cancel_trade_new", use_container_width=True):
                st.session_state["trade_open_section"] = None
                st.rerun()

    elif open_section == "edit":
        panel = st.container(border=True)
        with panel:
            hdr1, hdr2 = st.columns([4, 1])
            hdr1.subheader("Edit Previous Entry")
            if hdr2.button("Close", key="tj_close_edit"):
                st.session_state["trade_open_section"] = None
                st.rerun()

            if trades_df.empty:
                st.warning("No saved trades yet.")
                return

            options = trades_df.sort_values(["trade_date", "id"], ascending=[False, False])
            labels = {int(row["id"]): f'{row["trade_date"]} | {row["ticker"]} | {row["trade_type"]} | ID {int(row["id"])}' for _, row in options.iterrows()}
            selected_trade_id = st.selectbox("Select trade", options=list(labels.keys()), format_func=lambda x: labels[x], key="tj_edit_select_trade")

            row = trades_df[trades_df["id"] == selected_trade_id].iloc[0]
            base = row.to_dict()

            row1 = st.columns(4)
            trade_date = row1[0].date_input("Date", value=base["trade_date"], key="tj_date_edit")
            ticker = row1[1].text_input("Ticker", value=base["ticker"], key="tj_ticker_edit")
            trade_type = row1[2].selectbox("Trade Type", TRADE_TYPES, index=TRADE_TYPES.index(base["trade_type"]), key="tj_type_edit")
            direction = row1[3].selectbox("Direction", DIRECTIONS, index=DIRECTIONS.index(base["direction"]), key="tj_direction_edit")

            row2 = st.columns(3)
            quantity = row2[0].number_input("Quantity", min_value=0.0, value=float(base["quantity"]), step=1.0, key="tj_qty_edit")
            entry_price = row2[1].number_input("Entry Price", min_value=0.0, value=float(base["entry_price"]), step=0.01, key="tj_entry_edit")
            exit_price = row2[2].number_input("Exit Price", min_value=0.0, value=float(base["exit_price"]), step=0.01, key="tj_exit_edit")

            option_side = strike = expiration_date = None
            if trade_type == "Options":
                row3 = st.columns(3)
                opt_index = OPTION_SIDES.index(base["option_side"]) if base.get("option_side") in OPTION_SIDES else 0
                option_side = row3[0].selectbox("Option Side", OPTION_SIDES, index=opt_index, key="tj_opt_side_edit")
                strike = row3[1].number_input("Strike", min_value=0.0, value=float(base["strike"] or 0.0), step=0.5, key="tj_strike_edit")
                expiration_date = row3[2].date_input("Expiration Date", value=base["expiration_date"] if pd.notnull(base["expiration_date"]) else date.today(), key="tj_exp_edit")

            tag_col1, tag_col2 = st.columns(2)
            with tag_col1:
                mistake_categories = st.multiselect("Mistake Categories", list(MISTAKE_TAGS_BY_CATEGORY.keys()), default=base["mistake_categories"], key="tj_mcat_edit")
                available_mistake_tags = sorted({tag for cat in mistake_categories for tag in MISTAKE_TAGS_BY_CATEGORY.get(cat, {}).keys()})
                default_mistake_tags = [t for t in base["mistake_tags"] if t in available_mistake_tags]
                mistake_tags = st.multiselect("Mistake Tags", available_mistake_tags, default=default_mistake_tags, key="tj_mtags_edit")
            with tag_col2:
                edge_categories = st.multiselect("Edge Categories", list(EDGE_TAGS_BY_CATEGORY.keys()), default=base["edge_categories"], key="tj_ecat_edit")
                available_edge_tags = sorted({tag for cat in edge_categories for tag in EDGE_TAGS_BY_CATEGORY.get(cat, {}).keys()})
                default_edge_tags = [t for t in base["edge_tags"] if t in available_edge_tags]
                edge_tags = st.multiselect("Edge Tags", available_edge_tags, default=default_edge_tags, key="tj_etags_edit")

            notes = st.text_area("Notes", value=base["notes"], key="tj_notes_edit", height=140)
            score = discipline_score_from_tags(mistake_tags, edge_tags)
            st.metric("Auto Discipline Score", f"{score:.2f}")

            a1, a2, a3 = st.columns(3)
            if a1.button("Save Changes", type="primary", key="save_trade_edit", use_container_width=True):
                if not ticker.strip():
                    st.error("Ticker is required.")
                else:
                    saved_score = upsert_trade(user_email, selected_trade_id, trade_date, ticker, trade_type,
                                               direction, quantity, entry_price, exit_price, option_side,
                                               strike, expiration_date, mistake_categories, mistake_tags,
                                               edge_categories, edge_tags, notes)
                    st.success(f"Trade saved. Discipline Score: {saved_score:.2f}")
                    st.session_state["trade_open_section"] = None
                    st.rerun()
            if a2.button("Delete Trade", key="delete_trade_edit", use_container_width=True):
                delete_trade(user_email, int(selected_trade_id))
                st.success("Trade deleted.")
                st.session_state["trade_open_section"] = None
                st.rerun()
            if a3.button("Cancel", key="cancel_trade_edit", use_container_width=True):
                st.session_state["trade_open_section"] = None
                st.rerun()
    else:
        st.info("Choose New Entry or Edit Previous Entry to open the form.")


def page_trade_history(user_email: str):
    st.title("Trade History")
    trades_df = get_all_trades(user_email)

    if trades_df.empty:
        st.info("No Trade Journal data yet.")
        return

    min_date = trades_df["trade_date"].min()
    max_date = trades_df["trade_date"].max()

    c1, c2, c3 = st.columns(3)
    start_date = c1.date_input("Start date", value=min_date, min_value=min_date, max_value=max_date)
    end_date = c2.date_input("End date", value=max_date, min_value=min_date, max_value=max_date)
    tickers = sorted([t for t in trades_df["ticker"].dropna().unique().tolist() if str(t).strip()])
    ticker_filter = c3.multiselect("Ticker filter", tickers)

    all_mistake_tags = sorted({tag for tags in trades_df["mistake_tags"] for tag in tags})
    all_edge_tags = sorted({tag for tags in trades_df["edge_tags"] for tag in tags})

    c4, c5, c6 = st.columns(3)
    mistake_filter = c4.multiselect("Mistake tag filter", all_mistake_tags)
    edge_filter = c5.multiselect("Edge tag filter", all_edge_tags)
    min_discipline = c6.slider("Minimum discipline score", 0.0, 100.0, 0.0, 1.0)

    filtered = trades_df[
        (trades_df["trade_date"] >= start_date) &
        (trades_df["trade_date"] <= end_date) &
        (trades_df["discipline_score"] >= min_discipline)
    ].copy()

    if ticker_filter:
        filtered = filtered[filtered["ticker"].isin(ticker_filter)]
    if mistake_filter:
        filtered = filtered[filtered["mistake_tags"].apply(lambda tags: any(t in tags for t in mistake_filter))]
    if edge_filter:
        filtered = filtered[filtered["edge_tags"].apply(lambda tags: any(t in tags for t in edge_filter))]

    display = pd.DataFrame({
        "Date": filtered["trade_date"],
        "Ticker": filtered["ticker"],
        "Trade Type": filtered["trade_type"],
        "Direction": filtered["direction"],
        "Quantity": filtered["quantity"],
        "Entry Price": filtered["entry_price"],
        "Exit Price": filtered["exit_price"],
        "Mistake Tags": filtered["mistake_tags"].apply(lambda x: ", ".join(x)),
        "Edge Tags": filtered["edge_tags"].apply(lambda x: ", ".join(x)),
        "Discipline Score": filtered["discipline_score"],
        "Notes": filtered["notes"],
    })

    st.dataframe(
        display, use_container_width=True, hide_index=True,
        column_config={
            "Date": st.column_config.DateColumn("Date"),
            "Quantity": st.column_config.NumberColumn("Quantity", format="%.2f"),
            "Entry Price": st.column_config.NumberColumn("Entry Price", format="$%.2f"),
            "Exit Price": st.column_config.NumberColumn("Exit Price", format="$%.2f"),
            "Discipline Score": st.column_config.NumberColumn("Discipline Score", format="%.2f"),
            "Notes": st.column_config.TextColumn("Notes", width="large"),
        },
    )


def page_growth_projection(user_email: str):
    st.title("Growth Projection")
    settings = load_settings(user_email)
    daily_df = get_daily_metrics(user_email)

    chart, latest_ending, avg_daily_pct = build_projection_chart(
        daily_df, float(settings["starting_balance"]), int(settings["tracking_days"]), height=420
    )
    st.altair_chart(chart, use_container_width=True)

    trading_days_completed = len(daily_df)
    trading_days_left = max(int(settings["tracking_days"]) - trading_days_completed, 0)
    projected_end = latest_ending * ((1 + avg_daily_pct) ** trading_days_left)

    c1, c2, c3 = st.columns(3)
    c1.metric("Average Daily %", fmt_pct(avg_daily_pct))
    c2.metric("Trading Days Left", f"{trading_days_left:,}")
    c3.metric("Projected End Balance", fmt_money(projected_end))


def page_ai_psychology_review(user_email: str):
    st.markdown(
        """
        <div class="caplytix-card" style="margin-bottom:1.5rem;">
            <div class="caplytix-kicker">Behavior Intelligence</div>
            <h3 style="font-size:1.5rem;">AI Psychology Review</h3>
            <p>This review combines Daily Performance results with Trade Journal behavior to surface strengths, leaks, and coaching actions.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    daily_df = get_daily_metrics(user_email)
    trades_df = get_all_trades(user_email)
    review = psychology_review(daily_df, trades_df)
    scorecard = get_ai_scorecard(daily_df, trades_df)
    top_mistakes, top_edges = get_top_tag_counts(trades_df)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Performance Score", f"{scorecard['Performance Score']}/100")
    m2.metric("Discipline Score", f"{scorecard['Discipline Score']}/100")
    m3.metric("Consistency Score", f"{scorecard['Consistency Score']}/100")
    m4.metric("Process Score", f"{scorecard['Process Score']}/100")

    st.markdown('<div class="caplytix-divider"></div>', unsafe_allow_html=True)

    lead_left, lead_right = st.columns([1.3, 1])
    with lead_left:
        render_section_card("Tailored Summary", review["Tailored Summary"], kicker="Executive Read")
        render_section_card("Trading Style Profile", review["Trading Style Profile"], kicker="Style Read")
    with lead_right:
        render_section_card("Primary Focus", get_focus_message(scorecard), kicker="Current Priority")
        if trades_df.empty:
            render_section_card("Tag Read", "No Trade Journal tags yet.", kicker="Pattern Signals")
        else:
            mistake_text = ", ".join([f"{tag} ({count})" for tag, count in top_mistakes]) if top_mistakes else "None yet."
            edge_text = ", ".join([f"{tag} ({count})" for tag, count in top_edges]) if top_edges else "None yet."
            render_section_card("Tag Read", f"Most repeated mistake tags: {mistake_text} Most repeated edge tags: {edge_text}", kicker="Pattern Signals")

    st.markdown('<div class="caplytix-divider"></div>', unsafe_allow_html=True)

    row1, row2 = st.columns(2)
    with row1:
        render_section_card("Strengths", review["Strengths"], kicker="What Helps You")
    with row2:
        render_section_card("Weaknesses", review["Weaknesses"], kicker="What Hurts You")

    row3, row4 = st.columns(2)
    with row3:
        render_section_card("Pattern Breakdown", review["Pattern Breakdown"], kicker="Repeated Behavior")
    with row4:
        render_section_card("Coaching Actions", review["Coaching Actions"], kicker="Action Plan")

    st.markdown('<div class="caplytix-divider"></div>', unsafe_allow_html=True)

    if not daily_df.empty:
        trend_df = daily_df[["Date", "Daily %"]].copy()
        trend_df["Daily %"] = trend_df["Daily %"] * 100
        trend_chart = (
            alt.Chart(trend_df).mark_bar()
            .encode(
                x=alt.X("Date:T", title="Date"),
                y=alt.Y("Daily %:Q", title="Daily %"),
                tooltip=[alt.Tooltip("Date:T"), alt.Tooltip("Daily %:Q", format=".2f")],
            ).properties(height=260)
        )
        render_section_card("Result Rhythm", "Daily percentage outcome rhythm from Daily Performance.", kicker="Performance Trend")
        st.altair_chart(trend_chart, use_container_width=True)

    if not trades_df.empty:
        discipline_df = trades_df[["trade_date", "discipline_score"]].rename(columns={"trade_date": "Date", "discipline_score": "Discipline Score"})
        discipline_chart = (
            alt.Chart(discipline_df).mark_line(point=True)
            .encode(
                x=alt.X("Date:T", title="Trade Date"),
                y=alt.Y("Discipline Score:Q", scale=alt.Scale(domain=[0, 100])),
                tooltip=[alt.Tooltip("Date:T"), alt.Tooltip("Discipline Score:Q", format=".2f")],
            ).properties(height=260)
        )
        render_section_card("Discipline Trend", "Journaled discipline over time.", kicker="Behavior Trend")
        st.altair_chart(discipline_chart, use_container_width=True)


def page_settings(user_email: str):
    st.title("Settings")
    settings = load_settings(user_email)

    st.subheader("Core Settings")
    c1, c2 = st.columns(2)
    starting_balance = c1.number_input("Original Starting Account Balance", min_value=0.0, value=float(settings["starting_balance"]), step=100.0)
    preset = c2.selectbox("Tracking Period Length", options=list(TRACKING_PRESETS.keys()), index=list(TRACKING_PRESETS.keys()).index(settings["tracking_preset"]))

    if preset == "Custom":
        tracking_days = st.number_input("Custom Tracking Days", min_value=1, value=int(settings["tracking_days"]), step=1)
    else:
        tracking_days = TRACKING_PRESETS[preset]

    projection_method = st.selectbox("Projection Method", ["Average Daily %"], index=0)

    if st.button("Save Settings", type="primary"):
        set_setting("starting_balance", str(float(starting_balance)), user_email)
        set_setting("tracking_preset", preset, user_email)
        set_setting("tracking_days", str(int(tracking_days)), user_email)
        set_setting("projection_method", projection_method, user_email)
        st.success("Settings saved.")
        st.rerun()

    show_weight_tables()

    st.subheader("Data Management")
    st.warning("These actions permanently delete your data and cannot be undone.")
    d1, d2, d3 = st.columns(3)
    if d1.button("Reset Daily Performance Data"):
        reset_table("daily_performance", user_email)
        st.success("Daily Performance data reset.")
        st.rerun()
    if d2.button("Reset Trade Journal Data"):
        reset_table("trade_journal", user_email)
        st.success("Trade Journal data reset.")
        st.rerun()
    if d3.button("Reset All Data"):
        reset_table("daily_performance", user_email)
        reset_table("trade_journal", user_email)
        st.success("All data reset.")
        st.rerun()


# -----------------------------
# Main
# -----------------------------
def main():
    init_db()
    ensure_state()
    inject_global_styles()

    if not getattr(st.user, "is_logged_in", False):
        params = _get_query_params()
        requested_view = str(params.get("view", "landing")).lower()
        if requested_view == "login":
            render_login_page()
        else:
            render_landing_page()
        return

    st.session_state["entered_app"] = True

    try:
        st.query_params.clear()
    except Exception:
        pass

    if not is_allowed_user():
        st.error("This Google account is not authorized for Caplytix.")
        st.write(f"Signed in as: {get_current_user_email()}")
        if st.button("Log out"):
            st.logout()
        return

    user_email = get_current_user_email()

    with st.sidebar:
        render_sidebar_logo()
        st.markdown('<div class="caplytix-divider"></div>', unsafe_allow_html=True)
        st.caption(f"Signed in as: {user_email}")
        page = st.radio("Navigate", PAGES, index=0, label_visibility="collapsed")
        st.markdown('<div class="sidebar-spacer"></div>', unsafe_allow_html=True)
        if st.button("Logout", use_container_width=True):
            st.logout()

    if page == "Dashboard":
        page_dashboard(user_email)
    elif page == "Daily Performance":
        page_daily_performance(user_email)
    elif page == "Performance History":
        page_performance_history(user_email)
    elif page == "Trade Journal":
        page_trade_journal(user_email)
    elif page == "Trade History":
        page_trade_history(user_email)
    elif page == "Growth Projection":
        page_growth_projection(user_email)
    elif page == "AI Psychology Review":
        page_ai_psychology_review(user_email)
    elif page == "Settings":
        page_settings(user_email)


if __name__ == "__main__":
    main()
