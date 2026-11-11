from fastapi import APIRouter, Response
from app.schemas.responses import CareerCatalogResponse
from .dependencies import Backend

router = APIRouter(prefix='/career-profiles', tags=['CWA careers'])


@router.get('', response_model=CareerCatalogResponse)
def list_careers(backend: Backend, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return {'profiles': backend.persistent.careers.list_profiles()}
