#!/usr/bin/env python3
"""
Streamlit Cloud Deployment Entry Point

This is the main entry point for Streamlit Cloud deployment.
It runs both the FastAPI backend and serves the React frontend as static files.

The existing React frontend (Phase 5) and FastAPI backend (Phase 4) remain completely unchanged.
"""

import os
import sys
import threading
import time
import json
from pathlib import Path
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
import requests

# Must be the first Streamlit command
st.set_page_config(
    page_title="Mutual Fund FAQ Chatbot",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Initialize session state
if 'backend_started' not in st.session_state:
    st.session_state.backend_started = False
if 'messages' not in st.session_state:
    st.session_state.messages = [
        {
            "id": "welcome",
            "role": "assistant",
            "content": "Hello! I'm your Mutual Fund FAQ Assistant. I can help you with factual information about HDFC mutual funds on INDMoney. What would you like to know?",
            "sources": [],
            "timestamp": datetime.now().isoformat(),
        }
    ]
if 'funds' not in st.session_state:
    st.session_state.funds = []
if 'system_status' not in st.session_state:
    st.session_state.system_status = None

# Backend URL (localhost since backend runs in same container)
API_BASE_URL = "http://localhost:8000"


def start_backend_server():
    """Start the FastAPI backend server in a background thread."""
    if st.session_state.backend_started:
        return
    
    def run_server():
        import uvicorn
        from phase4.main import app
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
    
    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    st.session_state.backend_started = True
    
    # Wait for server to start
    time.sleep(2)


def check_backend():
    """Check if backend is running."""
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=3)
        return response.status_code == 200
    except:
        return False


def fetch_funds():
    """Fetch funds from backend."""
    try:
        response = requests.get(f"{API_BASE_URL}/funds", timeout=5)
        if response.status_code == 200:
            return response.json().get("funds", [])
    except:
        pass
    return []


def fetch_status():
    """Fetch system status from backend."""
    try:
        response = requests.get(f"{API_BASE_URL}/status", timeout=5)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None


def send_message(message: str):
    """Send message to backend and get response."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/chat/query",
            json={"message": message},
            timeout=30
        )
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        return {"answer": f"Error: {str(e)}", "sources": [], "metadata": {}}
    return {"answer": "Sorry, I encountered an error.", "sources": [], "metadata": {}}


# Start backend
start_backend_server()

# Check backend status
backend_online = check_backend()

# Load data if backend is online
if backend_online and not st.session_state.funds:
    st.session_state.funds = fetch_funds()
    st.session_state.system_status = fetch_status()

# Custom CSS matching the React app theme
st.markdown("""
<style>
    /* Hide Streamlit elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stDeployButton {display: none;}
    
    /* Main container */
    .main .block-container {
        padding: 0;
        max-width: 100%;
    }
    
    /* Chat container */
    .chat-container {
        display: flex;
        height: calc(100vh - 100px);
        background: #1a1d29;
    }
    
    /* Sidebar */
    .sidebar {
        width: 280px;
        background: #252a3a;
        border-right: 1px solid #3d445c;
        padding: 20px;
        overflow-y: auto;
    }
    
    /* Main chat area */
    .chat-main {
        flex: 1;
        display: flex;
        flex-direction: column;
        min-width: 0;
    }
    
    /* Header */
    .chat-header {
        padding: 16px 24px;
        background: #252a3a;
        border-bottom: 1px solid #3d445c;
    }
    
    .header-title {
        color: white;
        font-size: 16px;
        font-weight: 600;
        margin: 0;
    }
    
    .header-subtitle {
        color: #a0a8c0;
        font-size: 13px;
        margin: 4px 0 0 0;
    }
    
    /* Messages area */
    .messages-area {
        flex: 1;
        overflow-y: auto;
        padding: 24px;
        display: flex;
        flex-direction: column;
        gap: 16px;
    }
    
    /* Message bubbles */
    .message {
        display: flex;
        gap: 12px;
        max-width: 80%;
    }
    
    .message.user {
        align-self: flex-end;
        flex-direction: row-reverse;
        margin-left: auto;
    }
    
    .message.assistant {
        align-self: flex-start;
    }
    
    .message-avatar {
        width: 36px;
        height: 36px;
        background: linear-gradient(135deg, #6366f1, #4f46e5);
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 600;
        font-size: 12px;
        color: white;
        flex-shrink: 0;
    }
    
    .message-content {
        background: #2d3348;
        padding: 16px;
        border-radius: 12px;
        color: white;
        font-size: 14px;
        line-height: 1.6;
    }
    
    .message.user .message-content {
        background: #6366f1;
    }
    
    /* Sources */
    .sources-section {
        margin-top: 12px;
        padding-top: 12px;
        border-top: 1px solid #3d445c;
    }
    
    .sources-title {
        font-size: 12px;
        color: #a0a8c0;
        margin-bottom: 8px;
    }
    
    .source-link {
        color: #6366f1;
        font-size: 12px;
        text-decoration: none;
        word-break: break-all;
    }
    
    /* Input area */
    .input-area {
        padding: 16px 24px;
        background: #252a3a;
        border-top: 1px solid #3d445c;
    }
    
    /* Disclaimer */
    .disclaimer {
        padding: 12px 24px;
        background: rgba(99, 102, 241, 0.1);
        border-bottom: 1px solid #3d445c;
        font-size: 13px;
        color: #a0a8c0;
    }
    
    /* Status bar */
    .status-bar {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        background: #1a1d29;
        color: #a0a8c0;
        padding: 8px 20px;
        font-size: 12px;
        border-top: 1px solid #3d445c;
        display: flex;
        justify-content: space-between;
        align-items: center;
        z-index: 1000;
    }
    
    .status-indicator {
        display: flex;
        align-items: center;
        gap: 6px;
    }
    
    .status-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
    }
    
    .status-dot.online { background: #10b981; box-shadow: 0 0 4px #10b981; }
    .status-dot.offline { background: #ef4444; }
    .status-dot.warning { background: #f59e0b; }
    
    /* Fund buttons */
    .fund-button {
        width: 100%;
        padding: 12px;
        margin-bottom: 8px;
        background: #2d3348;
        border: 1px solid transparent;
        border-radius: 8px;
        color: white;
        text-align: left;
        cursor: pointer;
        transition: all 0.2s;
    }
    
    .fund-button:hover {
        border-color: #6366f1;
    }
    
    .fund-name {
        font-size: 13px;
        font-weight: 500;
    }
    
    /* Streamlit overrides */
    .stTextInput > div > div > input {
        background: #2d3348;
        border: 1px solid #3d445c;
        color: white;
        border-radius: 24px;
        padding: 12px 20px;
    }
    
    .stButton > button {
        background: #6366f1;
        color: white;
        border-radius: 50%;
        width: 40px;
        height: 40px;
        border: none;
    }
    
    .stSpinner > div {
        border-color: #6366f1;
    }
</style>
""", unsafe_allow_html=True)


# Main UI
if not backend_online:
    st.error("""
    ## ⚠️ Backend Starting...
    
    The backend server is starting up. Please wait a moment and refresh the page.
    
    If this persists, check the logs for errors.
    """)
else:
    # Layout
    col1, col2 = st.columns([1, 3])
    
    # Sidebar with funds
    with col1:
        st.markdown("<div class='sidebar'>", unsafe_allow_html=True)
        st.markdown("<h3 style='color: #a0a8c0; font-size: 14px; margin-bottom: 16px;'>📊 Available Funds</h3>", unsafe_allow_html=True)
        
        for fund in st.session_state.funds:
            fund_name = fund.get('name', 'Unknown Fund')
            if st.button(fund_name, key=fund['scheme_id'], use_container_width=True):
                prompt = f"Tell me about {fund_name}"
                st.session_state.messages.append({
                    "id": str(int(datetime.now().timestamp())),
                    "role": "user",
                    "content": prompt,
                    "sources": [],
                    "timestamp": datetime.now().isoformat()
                })
                
                with st.spinner("Thinking..."):
                    response = send_message(prompt)
                
                st.session_state.messages.append({
                    "id": str(int(datetime.now().timestamp()) + 1),
                    "role": "assistant",
                    "content": response.get("answer", "No response"),
                    "sources": response.get("sources", []),
                    "metadata": response.get("metadata", {}),
                    "timestamp": datetime.now().isoformat()
                })
                st.rerun()
        
        st.markdown("</div>", unsafe_allow_html=True)
    
    # Main chat area
    with col2:
        # Header
        st.markdown("""
        <div class='chat-header'>
            <h1 class='header-title'>💰 Mutual Fund Assistant</h1>
            <p class='header-subtitle'>Factual information about HDFC mutual funds</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Disclaimer
        st.markdown("""
        <div class='disclaimer'>
            ℹ️ This chatbot is a facts-only FAQ assistant. It does not provide investment advice or handle personal/account-specific queries.
        </div>
        """, unsafe_allow_html=True)
        
        # Messages
        messages_container = st.container()
        with messages_container:
            for msg in st.session_state.messages:
                role_class = msg['role']
                avatar = "👤" if msg['role'] == 'user' else "🤖"
                
                sources_html = ""
                if msg.get('sources'):
                    sources_html = "<div class='sources-section'><div class='sources-title'>Sources:</div>"
                    for source in msg['sources']:
                        sources_html += f"<div><a href='{source}' target='_blank' class='source-link'>{source}</a></div>"
                    sources_html += "</div>"
                
                st.markdown(f"""
                <div class='message {role_class}'>
                    <div class='message-avatar'>{avatar}</div>
                    <div class='message-content'>
                        {msg['content']}
                        {sources_html}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        
        # Input area
        st.markdown("<div class='input-area'>", unsafe_allow_html=True)
        
        col_input, col_button = st.columns([5, 1])
        with col_input:
            user_input = st.text_input("Ask a question...", key="user_input", label_visibility="collapsed")
        with col_button:
            send_clicked = st.button("➤", use_container_width=True)
        
        st.markdown("</div>", unsafe_allow_html=True)
        
        # Handle send
        if send_clicked and user_input.strip():
            # Add user message
            st.session_state.messages.append({
                "id": str(int(datetime.now().timestamp())),
                "role": "user",
                "content": user_input,
                "sources": [],
                "timestamp": datetime.now().isoformat()
            })
            
            # Get response
            with st.spinner("Thinking..."):
                response = send_message(user_input)
            
            # Add assistant message
            st.session_state.messages.append({
                "id": str(int(datetime.now().timestamp()) + 1),
                "role": "assistant",
                "content": response.get("answer", "No response"),
                "sources": response.get("sources", []),
                "metadata": response.get("metadata", {}),
                "timestamp": datetime.now().isoformat()
            })
            
            # Clear input and rerun
            st.rerun()

# Status bar
freshness = st.session_state.system_status.get('data_freshness', 'unknown') if st.session_state.system_status else 'unknown'
last_updated = ""
if st.session_state.system_status and st.session_state.system_status.get('last_updated'):
    dt = datetime.fromisoformat(st.session_state.system_status['last_updated'].replace('Z', '+00:00'))
    last_updated = f" | Data updated: {dt.strftime('%d %b %Y, %H:%M')}"

freshness_class = 'online' if freshness == 'fresh' else 'warning' if freshness == 'stale' else 'offline'

st.markdown(f"""
<div class='status-bar'>
    <div class='status-indicator'>
        <div class='status-dot {"online" if backend_online else "offline"}'></div>
        <span>Backend {"Online" if backend_online else "Offline"}</span>
    </div>
    <div class='status-indicator'>
        <div class='status-dot {freshness_class}'></div>
        <span>Data {freshness.title()}{last_updated}</span>
    </div>
    <div>{len(st.session_state.funds)} funds available</div>
</div>
""", unsafe_allow_html=True)
