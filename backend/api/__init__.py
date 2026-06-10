from typing import Any, Dict

# Shared application state — populated during FastAPI lifespan startup
app_state: Dict[str, Any] = {}
