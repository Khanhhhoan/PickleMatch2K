from fastapi import APIRouter
from app.api.v1.endpoints import auth, users, venues, search, bookings, recommendations, matches, ml, ws, payments

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(venues.router, prefix="/venues", tags=["venues"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(bookings.router, prefix="/bookings", tags=["bookings"])
api_router.include_router(recommendations.router, prefix="/recommendations", tags=["recommendations"])
api_router.include_router(matches.router, prefix="/matches", tags=["matches"])
api_router.include_router(ml.router, prefix="/ml", tags=["ml"])
api_router.include_router(ws.router, prefix="/ws", tags=["ws"])
api_router.include_router(payments.router, prefix="/payments", tags=["payments"])


