"""Backward compatibility shim — import from domain modules."""

from app.models.billing import *  # noqa: F403
from app.models.dicom import *  # noqa: F403
from app.models.patient import *  # noqa: F403
from app.models.tenant import *  # noqa: F403
from app.models.user import *  # noqa: F403
from app.models.billing import AuditEvent  # noqa: F401
