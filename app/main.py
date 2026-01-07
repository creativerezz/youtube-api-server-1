import logging
import traceback
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import uvicorn

from app.core.config import settings
from app.routes.youtube import router as youtube_router
from app.routes.service import router as service_router
from app.routes.prompts import router as prompts_router
from app.routes.ai import router as ai_router
from app.routes.data_api import router as data_api_router
from app.routes.dubbing import router as dubbing_router

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# Shared HTTP client (will be set during lifespan)
http_client: httpx.AsyncClient = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown events."""
    global http_client
    # Startup
    logger.info("Starting up - initializing shared HTTP client")
    http_client = httpx.AsyncClient(
        timeout=30.0,
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)
    )
    yield
    # Shutdown
    logger.info("Shutting down - closing HTTP client")
    await http_client.aclose()


def get_http_client() -> httpx.AsyncClient:
    """Get the shared HTTP client instance."""
    global http_client
    if http_client is None:
        raise RuntimeError("HTTP client not initialized. Server may not have started properly.")
    return http_client


# Enrich Swagger-UI with nicer defaults
swagger_ui_parameters = {
    "docExpansion": "none",  # collapse routes by default
    "defaultModelsExpandDepth": -1,  # hide schemas section unless expanded
}

# Custom API metadata (will be visible in /docs)
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Easily fetch YouTube metadata, captions and timestamps. Paste **any** video URL or 11-character ID – no extra JSON required!",
    version="1.2.0",
    contact={
        "name": "Reza J.",
        "url": "https://github.com/creativerezz",
        "x-twitter": "https://x.com/creativerezz",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    swagger_ui_parameters=swagger_ui_parameters,
    lifespan=lifespan,
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add GZip compression for responses > 1KB
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global exception handler for unhandled exceptions
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Catch-all exception handler to prevent crashes.
    Logs the error and returns a safe error response.
    
    Note: HTTPException is handled separately by FastAPI, so this catches
    truly unexpected exceptions that could crash the server.
    """
    # Skip HTTPException - FastAPI handles it properly
    from fastapi import HTTPException
    if isinstance(exc, HTTPException):
        raise exc
    
    error_id = id(exc)  # Simple error ID for tracking
    error_traceback = traceback.format_exc()
    
    # Log the full error with traceback
    logger.error(
        f"Unhandled exception [{error_id}]: {type(exc).__name__}: {str(exc)}\n"
        f"Path: {request.url.path}\n"
        f"Method: {request.method}\n"
        f"Traceback:\n{error_traceback}"
    )
    
    # Return safe error response without exposing internal details
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An internal server error occurred. Please try again later.",
            "error_id": str(error_id),
            "type": "InternalServerError"
        }
    )

# Handler for validation errors (400 Bad Request)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors gracefully."""
    logger.warning(f"Validation error on {request.url.path}: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "detail": "Invalid request parameters",
            "errors": exc.errors()
        }
    )

# Include routers
app.include_router(youtube_router)
app.include_router(service_router)
app.include_router(prompts_router)
app.include_router(ai_router)
app.include_router(data_api_router)
app.include_router(dubbing_router)

@app.get("/", tags=["root"])
async def root():
    """Root endpoint that provides API information"""
    try:
        return {
            "message": f"Welcome to the {settings.PROJECT_NAME}",
            "version": "1.2.0",
            "docs": "/docs",
            "redoc": "/redoc",
            "service": "/service/info",
            "status": "/service/status",
            "health": "/health"
        }
    except Exception as e:
        logger.error(f"Unexpected error in root endpoint: {str(e)}", exc_info=True)
        # Even if there's an error, try to return basic info
        return {
            "message": "Welcome to the YouTube Tools API",
            "version": "1.2.0",
            "status": "error",
            "health": "/health"
        }

@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint - should always return healthy if server is running"""
    try:
        return {"status": "healthy"}
    except Exception as e:
        logger.error(f"Unexpected error in health check: {str(e)}", exc_info=True)
        # Health check should be resilient - return unhealthy status instead of crashing
        return {"status": "unhealthy", "error": "Health check failed"}

def start():
    """Function to start the server"""
    logger.info(f"Starting server on {settings.HOST}:{settings.PORT}")
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)

if __name__ == "__main__":
    start()