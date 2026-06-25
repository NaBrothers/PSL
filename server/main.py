import uvicorn
from server.config import SERVER_PORT

if __name__ == "__main__":
    uvicorn.run("server.app:app", host="0.0.0.0", port=SERVER_PORT, reload=True)
