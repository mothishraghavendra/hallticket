"""
Server entry point.

Run directly:
    python server.py

Or via uvicorn:
    uvicorn app.main:app --host :: --port 8000 --reload
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


def get_local_ipv6() -> str | None:
    """Detect the routed IPv6 address selected for outbound traffic."""
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_DGRAM) as connection:
            connection.connect(("2606:4700:4700::1111", 53))
            return connection.getsockname()[0]
    except OSError:
        return None


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    local_ip = get_local_ip()
    local_ipv6 = get_local_ipv6()

    print("=" * 64)
    print("  Hall Ticket Generator — FastAPI Server")
    print("=" * 64)
    print(f"  • Local:           http://localhost:{port}")
    print(f"  • Mobile / LAN IP: http://{local_ip}:{port}")
    print(f"  • Swagger Docs:    http://{local_ip}:{port}/docs")
    if local_ipv6:
        print(f"  • IPv6:            http://[{local_ipv6}]:{port}")
    print("=" * 64)
    print("  To access from your mobile phone on the same Wi-Fi:")
    print(f"  Open http://{local_ip}:{port} in your mobile browser.")
    print("=" * 64)

    uvicorn.run(
        "app.main:app",
        host=os.environ.get("HOST", "::"),
        port=port,
        reload=True,
        log_level="info",
    )
