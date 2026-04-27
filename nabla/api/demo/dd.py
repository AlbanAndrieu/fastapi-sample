from fastapi import APIRouter

from nabla.utils.logger import logger

from nabla.dd.dd_api_exporter import get_products

router = APIRouter()


@router.get("/internal-api/dd")
def dd_internal_api():
    logger.info("Get dd products")

    return get_products()
