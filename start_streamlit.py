#!/usr/bin/env python3
"""
Streamlit Deployment Startup Script

This script handles the deployment setup for Streamlit Cloud while keeping
the existing React frontend and FastAPI backend unchanged.

For Streamlit Cloud deployment, this script:
1. Starts the FastAPI backend as a background thread
2. Builds and serves the React frontend as static files
3. Launches the Streamlit wrapper app

For local development, use the separate terminals approach.
"""

import os
import sys
import subprocess
import threading
import time
import signal
from pathlib import Path

# Configuration
PROJECT_ROOT = Path(__file__).parent.absolute()
FRONTEND_DIR = PROJECT_ROOT / "phase5"
BACKEND_MODULE = "phase4.main"
STREAMLIT_APP = "streamlit_app.py"

# Environment variables
os.environ["PYTHONPATH"] = str(PROJECT_ROOT)
os.environ["API_BASE_URL"] = "http://localhost:8000"
os.environ["FRONTEND_URL"] = "http://localhost:5173"


def start_backend():
    """Start the FastAPI backend server."""
    print("🚀 Starting FastAPI backend...")
    try:
        import uvicorn
        from phase4.main import app
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
    except Exception as e:
        print(f"❌ Backend error: {e}")
        sys.exit(1)


def start_frontend_dev():
    """Start the React frontend development server."""
    print("🎨 Starting React frontend (dev mode)...")
    try:
        os.chdir(FRONTEND_DIR)
        subprocess.run(["npm", "run", "dev"], check=True)
    except Exception as e:
        print(f"❌ Frontend error: {e}")
        sys.exit(1)


def build_frontend():
    """Build the React frontend for production."""
    print("🔨 Building React frontend...")
    try:
        os.chdir(FRONTEND_DIR)
        # Install dependencies if node_modules doesn't exist
        if not (FRONTEND_DIR / "node_modules").exists():
            print("📦 Installing npm dependencies...")
            subprocess.run(["npm", "install"], check=True)
        # Build the frontend
        subprocess.run(["npm", "run", "build"], check=True)
        print("✅ Frontend build complete")
        return True
    except Exception as e:
        print(f"❌ Frontend build error: {e}")
        return False


def serve_frontend_static():
    """Serve the built frontend as static files."""
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse
    
    app = FastAPI()
    dist_dir = FRONTEND_DIR / "dist"
    
    # Mount static files
    app.mount("/assets", StaticFiles(directory=dist_dir / "assets"), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        return FileResponse(dist_dir / "index.html")
    
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5173, log_level="info")


def start_streamlit():
    """Start the Streamlit app."""
    print("🌊 Starting Streamlit...")
    try:
        os.chdir(PROJECT_ROOT)
        subprocess.run([
            sys.executable, "-m", "streamlit", "run", STREAMLIT_APP,
            "--server.port=8501",
            "--server.address=0.0.0.0"
        ], check=True)
    except Exception as e:
        print(f"❌ Streamlit error: {e}")
        sys.exit(1)


def main():
    """Main entry point."""
    print("=" * 60)
    print("RAG Mutual Fund FAQ Chatbot - Streamlit Deployment")
    print("=" * 60)
    
    # Check if we're in production mode (Streamlit Cloud)
    is_production = os.getenv("STREAMLIT_SHARING", "false").lower() == "true"
    
    if is_production:
        print("🌐 Running in production mode (Streamlit Cloud)")
        # In production, we need to build and serve frontend as static
        if build_frontend():
            # Start backend and frontend static server in threads
            backend_thread = threading.Thread(target=start_backend, daemon=True)
            frontend_thread = threading.Thread(target=serve_frontend_static, daemon=True)
            
            backend_thread.start()
            frontend_thread.start()
            
            # Wait for services to start
            time.sleep(3)
            
            # Start Streamlit (this blocks)
            start_streamlit()
        else:
            print("❌ Failed to build frontend")
            sys.exit(1)
    else:
        print("💻 Running in development mode")
        print("""
For local development, please run these commands in separate terminals:

Terminal 1 - Backend:
    python -m phase4.main

Terminal 2 - Frontend:
    cd phase5 && npm run dev

Terminal 3 - Streamlit:
    streamlit run streamlit_app.py

Or use this script with --all flag to start everything:
    python start_streamlit.py --all
        """)
        
        if "--all" in sys.argv:
            # Start everything in development mode
            backend_thread = threading.Thread(target=start_backend, daemon=True)
            frontend_thread = threading.Thread(target=start_frontend_dev, daemon=True)
            
            backend_thread.start()
            frontend_thread.start()
            
            # Wait for services to start
            time.sleep(5)
            
            # Start Streamlit (this blocks)
            start_streamlit()


if __name__ == "__main__":
    main()
