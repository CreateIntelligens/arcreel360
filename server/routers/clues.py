"""
線索管理路由
"""

import asyncio
import logging

logger = logging.getLogger(__name__)
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from lib import PROJECT_ROOT
from lib.project_change_hints import project_change_source
from lib.project_manager import ProjectManager
from server.auth import CurrentUser

router = APIRouter()

# 初始化專案管理器
pm = ProjectManager(PROJECT_ROOT / "projects")


def get_project_manager() -> ProjectManager:
    return pm


class CreateClueRequest(BaseModel):
    name: str
    description: str
    importance: str | None = "major"  # 'major' 或 'minor'


class UpdateClueRequest(BaseModel):
    description: str | None = None
    importance: str | None = None
    clue_sheet: str | None = None
    reference_image: str | None = None
    image_backend: str | None = None


@router.post("/projects/{project_name}/clues")
async def add_clue(project_name: str, req: CreateClueRequest, _user: CurrentUser):
    """新增線索"""
    try:

        def _sync():
            manager = get_project_manager()
            with project_change_source("webui"):
                created = manager.add_clue(project_name, req.name, req.description, req.importance)
            if not created:
                raise ValueError(f"線索 '{req.name}' 已存在")
            project = manager.load_project(project_name)
            return {"success": True, "clue": project["clues"][req.name]}

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


@router.patch("/projects/{project_name}/clues/{clue_name}")
async def update_clue(project_name: str, clue_name: str, req: UpdateClueRequest, _user: CurrentUser):
    """更新線索"""
    try:
        # 驗證輸入（純 CPU，無需下沉到執行緒）
        if req.importance is not None and req.importance not in ["major", "minor"]:
            raise HTTPException(status_code=400, detail="重要程度必須是 'major' 或 'minor'")

        def _sync():
            manager = get_project_manager()
            result_clue = {}

            def _mutate(project):
                if clue_name not in project.get("clues", {}):
                    raise KeyError(clue_name)
                clue = project["clues"][clue_name]
                if req.description is not None:
                    clue["description"] = req.description
                if req.importance is not None:
                    clue["importance"] = req.importance
                if req.clue_sheet is not None:
                    clue["clue_sheet"] = req.clue_sheet
                if req.reference_image is not None:
                    clue["reference_image"] = req.reference_image
                if req.image_backend is not None:
                    clue["image_backend"] = req.image_backend if req.image_backend else None
                result_clue.update(clue)

            with project_change_source("webui"):
                manager.update_project(project_name, _mutate)
            return {"success": True, "clue": result_clue}

        return await asyncio.to_thread(_sync)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"線索 '{clue_name}' 不存在")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"專案 '{project_name}' 不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


class RenameClueRequest(BaseModel):
    new_name: str


@router.post("/projects/{project_name}/clues/{clue_name}/rename")
async def rename_clue(
    project_name: str,
    clue_name: str,
    req: RenameClueRequest,
    _user: CurrentUser,
):
    """改名道具：搬移檔案、更新版本記錄、替換劇本引用、寫回 project.json。"""
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
                    kind="clue",
                    old_name=clue_name,
                    new_name=req.new_name,
                )
                manager.save_project(project_name, project)

            return {
                "success": True,
                "old_name": clue_name,
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


@router.delete("/projects/{project_name}/clues/{clue_name}")
async def delete_clue(project_name: str, clue_name: str, _user: CurrentUser):
    """刪除線索"""
    try:

        def _sync():
            manager = get_project_manager()

            def _mutate(project):
                if clue_name not in project.get("clues", {}):
                    raise KeyError(clue_name)
                del project["clues"][clue_name]

            with project_change_source("webui"):
                manager.update_project(project_name, _mutate)
            return {"success": True, "message": f"線索 '{clue_name}' 已刪除"}

        return await asyncio.to_thread(_sync)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"線索 '{clue_name}' 不存在")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"專案 '{project_name}' 不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


class BatchCreateClueRequest(BaseModel):
    items: list[CreateClueRequest]


@router.post("/projects/{project_name}/clues/batch_create")
async def batch_add_clues(project_name: str, req: BatchCreateClueRequest, _user: CurrentUser):
    """批次新增線索"""
    try:

        def _sync():
            manager = get_project_manager()

            def _mutate(project):
                clues = project.setdefault("clues", {})
                for item in req.items:
                    clues[item.name] = {
                        "description": item.description,
                        "importance": item.importance or "major",
                        "clue_sheet": "",
                    }

            with project_change_source("webui"):
                manager.update_project(project_name, _mutate)

            project = manager.load_project(project_name)
            return {"success": True, "clues": project.get("clues", {})}

        return await asyncio.to_thread(_sync)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"專案 '{project_name}' 不存在")
    except Exception as e:
        logger.exception("批次新增線索失敗")
        raise HTTPException(status_code=500, detail=str(e))
