"""
場景管理路由
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from lib import PROJECT_ROOT
from lib.project_change_hints import project_change_source
from lib.project_manager import ProjectManager
from server.auth import CurrentUser

logger = logging.getLogger(__name__)
router = APIRouter()

# 初始化專案管理器
pm = ProjectManager(PROJECT_ROOT / "projects")


def get_project_manager() -> ProjectManager:
    return pm


class CreateSceneRequest(BaseModel):
    name: str
    description: str


class UpdateSceneRequest(BaseModel):
    description: str | None = None
    scene_sheet: str | None = None
    scene_ref: str | None = None
    image_backend: str | None = None


class RenameSceneRequest(BaseModel):
    new_name: str


@router.post("/projects/{project_name}/project-scenes")
async def add_scene(project_name: str, req: CreateSceneRequest, _user: CurrentUser):
    """新增場景"""
    try:

        def _sync():
            manager = get_project_manager()
            created: dict = {}

            def _mutate(project: dict) -> None:
                scenes = project.setdefault("scenes", {})
                if req.name in scenes:
                    raise ValueError(f"場景 '{req.name}' 已存在")
                scenes[req.name] = {
                    "description": req.description,
                    "scene_sheet": "",
                    "scene_ref": "",
                }
                created.update(scenes[req.name])

            with project_change_source("webui"):
                manager.update_project(project_name, _mutate)
            return {"success": True, "scene": created}

        return await asyncio.to_thread(_sync)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"專案 '{project_name}' 不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/projects/{project_name}/project-scenes/{scene_name}")
async def update_scene(project_name: str, scene_name: str, req: UpdateSceneRequest, _user: CurrentUser):
    """更新場景"""
    try:

        def _sync():
            manager = get_project_manager()
            result_scene: dict = {}

            def _mutate(project):
                if scene_name not in project.get("scenes", {}):
                    raise KeyError(scene_name)
                scene = project["scenes"][scene_name]
                for field in ("description", "scene_sheet", "scene_ref", "image_backend"):
                    value = getattr(req, field)
                    if value is not None:
                        scene[field] = value if value else None
                result_scene.update(scene)

            with project_change_source("webui"):
                manager.update_project(project_name, _mutate)
            return {"success": True, "scene": result_scene}

        return await asyncio.to_thread(_sync)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"場景 '{scene_name}' 不存在")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"專案 '{project_name}' 不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_name}/project-scenes/{scene_name}/rename")
async def rename_scene(
    project_name: str,
    scene_name: str,
    req: RenameSceneRequest,
    _user: CurrentUser,
):
    """改名專案級場景：搬移檔案、更新版本記錄、替換劇本引用、寫回 project.json。"""
    from lib.resource_rename import rename_resource

    try:

        def _sync():
            manager = get_project_manager()
            project_path = manager.get_project_path(project_name)
            project = manager.load_project(project_name)

            with project_change_source("webui"):
                result = rename_resource(
                    project_path=project_path,
                    project=project,
                    kind="scene",
                    old_name=scene_name,
                    new_name=req.new_name,
                )
                manager.save_project(project_name, project)

            return {
                "success": True,
                "old_name": scene_name,
                "new_name": req.new_name,
                "files_moved": result.files_moved,
                "scripts_updated": result.scripts_updated,
                "versions_updated": result.versions_updated,
            }

        return await asyncio.to_thread(_sync)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"專案 '{project_name}' 不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/projects/{project_name}/project-scenes/{scene_name}")
async def delete_scene(project_name: str, scene_name: str, _user: CurrentUser):
    """刪除場景"""
    try:

        def _sync():
            manager = get_project_manager()

            def _mutate(project):
                if scene_name not in project.get("scenes", {}):
                    raise KeyError(scene_name)
                del project["scenes"][scene_name]

            with project_change_source("webui"):
                manager.update_project(project_name, _mutate)
            return {"success": True, "message": f"場景 '{scene_name}' 已刪除"}

        return await asyncio.to_thread(_sync)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"場景 '{scene_name}' 不存在")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"專案 '{project_name}' 不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


class BatchCreateSceneRequest(BaseModel):
    items: list[CreateSceneRequest]


@router.post("/projects/{project_name}/project-scenes/batch_create")
async def batch_add_scenes(project_name: str, req: BatchCreateSceneRequest, _user: CurrentUser):
    """批次新增場景"""
    try:

        def _sync():
            manager = get_project_manager()

            def _mutate(project):
                scenes = project.setdefault("scenes", {})
                for item in req.items:
                    scenes[item.name] = {
                        "description": item.description,
                        "scene_sheet": "",
                        "scene_ref": "",
                    }

            with project_change_source("webui"):
                manager.update_project(project_name, _mutate)

            project = manager.load_project(project_name)
            return {"success": True, "scenes": project.get("scenes", {})}

        return await asyncio.to_thread(_sync)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"專案 '{project_name}' 不存在")
    except Exception as e:
        logger.exception("批次新增場景失敗")
        raise HTTPException(status_code=500, detail=str(e))
