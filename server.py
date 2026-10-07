"""
Server entry point.

Run directly:
    python server.py

Or via uvicorn:
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

import os
import socket
import uvicorn


def get_local_ip() -> str:
    """Detect LAN IP address so users can easily test from their mobile device."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    local_ip = get_local_ip()

    print("=" * 64)
    print("  Hall Ticket Generator — FastAPI Server")
    print("=" * 64)
    print(f"  • Local:           http://localhost:{port}")
    print(f"  • Mobile / LAN IP: http://{local_ip}:{port}")
    print(f"  • Swagger Docs:    http://{local_ip}:{port}/docs")
    print("=" * 64)
    print("  To access from your mobile phone on the same Wi-Fi:")
    print(f"  Open http://{local_ip}:{port} in your mobile browser.")
    print("=" * 64)

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        workers=1,  # 1 worker — rembg ONNX session is not fork-safe
        log_level="info",
    )
