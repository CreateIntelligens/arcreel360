"""
角色管理路由
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


class CreateCharacterRequest(BaseModel):
    name: str
    description: str
    voice_style: str | None = ""


class UpdateCharacterRequest(BaseModel):
    description: str | None = None
    voice_style: str | None = None
    character_sheet: str | None = None
    reference_image: str | None = None
    image_backend: str | None = None


@router.post("/projects/{project_name}/characters")
async def add_character(project_name: str, req: CreateCharacterRequest, _user: CurrentUser):
    """新增角色"""
    try:

        def _sync():
            with project_change_source("webui"):
                project = get_project_manager().add_project_character(
                    project_name, req.name, req.description, req.voice_style
                )
            return {"success": True, "character": project["characters"][req.name]}

        return await asyncio.to_thread(_sync)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"專案 '{project_name}' 不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/projects/{project_name}/characters/{char_name}")
async def update_character(
    project_name: str,
    char_name: str,
    req: UpdateCharacterRequest,
    _user: CurrentUser,
):
    """更新角色"""
    try:

        def _sync():
            manager = get_project_manager()
            result_char = {}

            def _mutate(project):
                if char_name not in project.get("characters", {}):
                    raise KeyError(char_name)
                char = project["characters"][char_name]
                if req.description is not None:
                    char["description"] = req.description
                if req.voice_style is not None:
                    char["voice_style"] = req.voice_style
                if req.character_sheet is not None:
                    char["character_sheet"] = req.character_sheet
                if req.reference_image is not None:
                    char["reference_image"] = req.reference_image
                if req.image_backend is not None:
                    char["image_backend"] = req.image_backend if req.image_backend else None
                result_char.update(char)

            with project_change_source("webui"):
                manager.update_project(project_name, _mutate)
            return {"success": True, "character": result_char}

        return await asyncio.to_thread(_sync)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"角色 '{char_name}' 不存在")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"專案 '{project_name}' 不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


class RenameCharacterRequest(BaseModel):
    new_name: str


@router.post("/projects/{project_name}/characters/{char_name}/rename")
async def rename_character(
    project_name: str,
    char_name: str,
    req: RenameCharacterRequest,
    _user: CurrentUser,
):
    """改名角色：搬移檔案、更新版本記錄、替換劇本引用、寫回 project.json。"""
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
                    kind="character",
                    old_name=char_name,
                    new_name=req.new_name,
                )
                manager.save_project(project_name, project)

            return {
                "success": True,
                "old_name": char_name,
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


@router.delete("/projects/{project_name}/characters/{char_name}")
async def delete_character(project_name: str, char_name: str, _user: CurrentUser):
    """刪除角色"""
    try:

        def _sync():
            manager = get_project_manager()

            def _mutate(project):
                if char_name not in project.get("characters", {}):
                    raise KeyError(char_name)
                del project["characters"][char_name]

            with project_change_source("webui"):
                manager.update_project(project_name, _mutate)
            return {"success": True, "message": f"角色 '{char_name}' 已刪除"}

        return await asyncio.to_thread(_sync)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"角色 '{char_name}' 不存在")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"專案 '{project_name}' 不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


class BatchCreateCharacterRequest(BaseModel):
    items: list[CreateCharacterRequest]


@router.post("/projects/{project_name}/characters/batch_create")
async def batch_add_characters(project_name: str, req: BatchCreateCharacterRequest, _user: CurrentUser):
    """批次新增角色"""
    try:

        def _sync():
            manager = get_project_manager()

            def _mutate(project):
                chars = project.setdefault("characters", {})
                for item in req.items:
                    chars[item.name] = {
                        "description": item.description,
                        "voice_style": item.voice_style or "",
                        "character_sheet": "",
                    }

            with project_change_source("webui"):
                manager.update_project(project_name, _mutate)

            project = manager.load_project(project_name)
            return {"success": True, "characters": project.get("characters", {})}

        return await asyncio.to_thread(_sync)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"專案 '{project_name}' 不存在")
    except Exception as e:
        logger.exception("批次新增角色失敗")
        raise HTTPException(status_code=500, detail=str(e))
