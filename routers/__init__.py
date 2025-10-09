# routers/__init__.py
from .basic import basic_router
from .profile import profile_router
from .cardio import cardio_router
from .training import training_router
from .reports import reports_router
from .feedback import feedback_router

__all__ = [
    "basic_router",
    "profile_router",
    "training_router",
    "cardio_router",
    "reports_router",
    "feedback_router",
]
