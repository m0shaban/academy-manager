"""صفحة البوابة السرية (مخفية من القائمة)."""

import streamlit as st

from secret_gate_ui import render_secret_gate


st.set_page_config(
    page_title="🔒 البوابة السرية",
    page_icon="🔐",
    layout="centered",
    initial_sidebar_state="collapsed",
)

BACKEND_URL = st.secrets.get("BACKEND_URL", "https://your-render-app.onrender.com")

render_secret_gate(BACKEND_URL, standalone=True)
