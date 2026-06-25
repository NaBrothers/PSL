import uvicorn
from server.config import SERVER_PORT

uvicorn.run("server.app:app", host="0.0.0.0", port=SERVER_PORT, reload=True)
