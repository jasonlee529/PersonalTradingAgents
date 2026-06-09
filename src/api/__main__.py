import uvicorn
from src.config import settings
from src.api.main import create_app

if __name__ == "__main__":
    app = create_app(settings)
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
    )
