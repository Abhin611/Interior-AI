import uvicorn

if __name__ == '__main__':
    uvicorn.run(
        "app.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        timeout_keep_alive=600,
        ws_ping_interval=30,
        ws_ping_timeout=600,
    )