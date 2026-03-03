#!/usr/bin/env python3
"""
Streamlit Deployment Wrapper for RAG-Based Mutual Fund FAQ Chatbot

This Streamlit app serves as a wrapper that:
1. Embeds the existing React frontend via iframe
2. Provides status monitoring for the backend API
3. Displays data freshness information

The existing React frontend (Phase 5) and FastAPI backend (Phase 4) remain unchanged.
"""

import streamlit as st
import requests
import json
from datetime import datetime
import os

# Page configuration
st.set_page_config(
    page_title="Mutual Fund FAQ Chatbot",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Backend API URL (configurable via environment variable)
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# Custom CSS to hide Streamlit branding and make iframe full height
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stApp {
        margin-top: -80px;
    }
    .block-container {
        padding: 0;
        max-width: 100%;
    }
    iframe {
        width: 100%;
        height: 100vh;
        border: none;
    }
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
        z-index: 9999;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .status-indicator {
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }
    .status-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        display: inline-block;
    }
    .status-dot.online {
        background-color: #10b981;
        box-shadow: 0 0 4px #10b981;
    }
    .status-dot.offline {
        background-color: #ef4444;
        box-shadow: 0 0 4px #ef4444;
    }
    .status-dot.warning {
        background-color: #f59e0b;
        box-shadow: 0 0 4px #f59e0b;
    }
</style>
""", unsafe_allow_html=True)


def check_backend_status():
    """Check if the backend API is running."""
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            return True, response.json()
        return False, None
    except:
        return False, None


def get_system_status():
    """Get system status from backend."""
    try:
        response = requests.get(f"{API_BASE_URL}/status", timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None


# Check backend status
is_online, health_data = check_backend_status()
system_status = get_system_status() if is_online else None

# Sidebar with configuration (collapsed by default)
with st.sidebar:
    st.title("⚙️ Configuration")
    
    # API URL configuration
    new_api_url = st.text_input("Backend API URL", value=API_BASE_URL)
    if new_api_url != API_BASE_URL:
        st.info("Refresh the page to apply the new API URL")
        os.environ["API_BASE_URL"] = new_api_url
    
    st.divider()
    
    # Status information
    st.subheader("System Status")
    
    if is_online:
        st.success("✅ Backend Online")
        
        if system_status:
            st.write(f"**Total Funds:** {system_status.get('total_funds', 'N/A')}")
            
            freshness = system_status.get('data_freshness', 'unknown')
            if freshness == 'fresh':
                st.success("🟢 Data Fresh")
            elif freshness == 'stale':
                st.warning("🟡 Data Stale")
            else:
                st.info("⚪ Data Status Unknown")
            
            last_updated = system_status.get('last_updated')
            if last_updated:
                last_update_dt = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
                st.write(f"**Last Updated:** {last_update_dt.strftime('%d %b %Y, %H:%M')}")
    else:
        st.error("❌ Backend Offline")
        st.info("Please ensure the backend is running on the configured API URL")
    
    st.divider()
    
    # Links
    st.subheader("Links")
    st.markdown(f"[API Documentation]({API_BASE_URL}/docs)")
    st.markdown(f"[Health Check]({API_BASE_URL}/health)")


# Main content - Embed the React frontend
if is_online:
    # Determine the frontend URL
    # In production, this would be the URL where the built React app is hosted
    # For local development with Streamlit, we can serve the built files
    
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
    
    # Embed the React app via iframe
    st.components.v1.iframe(
        src=FRONTEND_URL,
        height=800,
        scrolling=True
    )
    
    # Status bar at the bottom
    freshness_class = system_status.get('data_freshness', 'unknown') if system_status else 'unknown'
    freshness_dot = 'online' if freshness_class == 'fresh' else 'warning' if freshness_class == 'stale' else 'offline'
    
    last_updated_str = ""
    if system_status and system_status.get('last_updated'):
        last_update_dt = datetime.fromisoformat(system_status['last_updated'].replace('Z', '+00:00'))
        last_updated_str = f" | Data updated: {last_update_dt.strftime('%d %b %Y, %H:%M')}"
    
    st.markdown(f"""
    <div class="status-bar">
        <div class="status-indicator">
            <span class="status-dot {'online' if is_online else 'offline'}"></span>
            <span>Backend {'Online' if is_online else 'Offline'}</span>
        </div>
        <div>
            <span class="status-dot {freshness_dot}"></span>
            <span>Data {freshness_class.title()}{last_updated_str}</span>
        </div>
        <div>API: {API_BASE_URL}</div>
    </div>
    """, unsafe_allow_html=True)
    
else:
    # Show error message when backend is offline
    st.error("""
    ## ⚠️ Backend Not Available
    
    The backend API is not responding. Please ensure:
    
    1. The backend server is running:
       ```bash
       python -m phase4.main
       ```
    
    2. The API URL is correct (check sidebar configuration)
    
    3. Check the API health endpoint: `{API_BASE_URL}/health`
    
    ### Quick Start
    
    To run locally:
    ```bash
    # Terminal 1: Start backend
    python -m phase4.main
    
    # Terminal 2: Start frontend
    cd phase5 && npm run dev
    
    # Terminal 3: Start Streamlit
    streamlit run streamlit_app.py
    ```
    """)

# Auto-refresh every 30 seconds to update status
st.empty()
