from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services.errors import BackendUnavailableError

bearer = HTTPBearer(auto_error=False, description="Selection capability returned only at selection creation.")


def backend(request: Request):
    value = request.app.state.backend
    if value is None:
        raise BackendUnavailableError("Backend database is unavailable")
    return value


def catalog(request: Request):
    value = request.app.state.catalog
    if value is None:
        raise BackendUnavailableError("Configure an explicit curriculum mapping and default curriculum")
    return value


def capability(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    if credentials is None or not credentials.credentials or len(credentials.credentials) > 256:
        raise HTTPException(status_code=401, detail="Capability bearer token required", headers={"WWW-Authenticate": "Bearer"})
    return credentials.credentials


def idempotency_key(value: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]):
    if not value.strip():
        raise HTTPException(status_code=422, detail="Idempotency-Key must not be blank")
    return value


Backend = Annotated[object, Depends(backend)]
Catalog = Annotated[object, Depends(catalog)]
Capability = Annotated[str, Depends(capability)]
IdempotencyKey = Annotated[str, Depends(idempotency_key)]
