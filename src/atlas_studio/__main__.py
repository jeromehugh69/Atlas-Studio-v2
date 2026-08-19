"""Run Atlas Studio standalone without Docker or uvicorn CLI."""
import os
import sys


def main():
    os.environ.setdefault("ATLAS_STUDIO_MODE", "community")
    try:
        import uvicorn
    except ImportError:
        print("ERROR: uvicorn is required. Install with: pip install uvicorn[standard]")
        sys.exit(1)
    uvicorn.run(
        "atlas_studio.main:app",
        host=os.getenv("ATLAS_STUDIO_HOST", "127.0.0.1"),
        port=int(os.getenv("ATLAS_STUDIO_PORT", "8080")),
        log_level="info",
    )


if __name__ == "__main__":
    main()
