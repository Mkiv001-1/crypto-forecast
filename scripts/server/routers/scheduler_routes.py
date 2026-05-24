"""Scheduler and circuit-breaker API routes."""

import logging

from fastapi import APIRouter, Body, Depends, HTTPException

from scripts.server.routers import common

logger = logging.getLogger(__name__)
router = APIRouter()

verify_api_key = common.verify_api_key
_get_db_manager = common.get_db_manager


@router.get("/scheduler/status", dependencies=[Depends(verify_api_key)])
async def get_scheduler_status():
    """Return running status of scheduler tasks."""
    try:
        from scripts.core.scheduler import get_task_status

        return {"tasks": get_task_status()}
    except Exception as e:
        return {"tasks": {}, "error": str(e)}


@router.get("/scheduler/tasks", dependencies=[Depends(verify_api_key)])
async def get_scheduler_tasks():
    """Return all scheduler tasks (DB catalog + live runtime status)."""
    try:
        from scripts.core.scheduler import list_scheduler_tasks_for_api

        em = _get_db_manager()
        items = list_scheduler_tasks_for_api(em)
        return {"items": items, "total": len(items)}
    except Exception as e:
        logger.exception("Error fetching scheduler tasks")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.patch("/scheduler/tasks/{name}/active", dependencies=[Depends(verify_api_key)])
async def set_task_active(name: str, body: dict = Body(...)):
    """Enable or disable a scheduled task (is_active 0 or 1)."""
    try:
        active = int(bool(body.get("active", 1)))
        em = _get_db_manager()
        with em._connect() as con:
            cur = con.execute(
                "UPDATE scheduled_tasks SET is_active=? WHERE name=?",
                (active, name),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail=f"Task '{name}' not found")
        return {"name": name, "is_active": active}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating task active state")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/circuit-breaker/status", dependencies=[Depends(verify_api_key)])
async def get_circuit_breaker_status():
    """Return OpenRouter circuit breaker state."""
    try:
        from scripts.core.circuit_breaker import status as cb_status

        return cb_status()
    except Exception as e:
        return {"state": "UNKNOWN", "error": str(e)}


@router.post("/circuit-breaker/reset", dependencies=[Depends(verify_api_key)])
async def reset_circuit_breaker():
    """Manually reset circuit breaker to CLOSED."""
    try:
        from scripts.core.circuit_breaker import reset as cb_reset

        cb_reset()
        return {"state": "CLOSED", "reset": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
