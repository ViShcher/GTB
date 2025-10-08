# routers/__init__.py
from .basic import basic_router
from .profile import profile_router
from .cardio import cardio_router
from .training import training_router
from .reports import reports_router
__all__ = [
    "basic_router",
    "profile_router",
    "training_router",
    "cardio_router",
    "reports_router",
]

# Порядок важен: cardio выше training, чтобы кардио-ввод не перехватывался силовым логгером
__all__ = ["basic_router", "profile_router", "cardio_router", "training_router"]
