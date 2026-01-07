from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query

from app.utils.prompt_service import get_prompt_service, PromptInfo

router = APIRouter(
    prefix="/prompts",
    tags=["prompts"],
    responses={404: {"description": "Not found"}},
)

@router.get(
    "/",
    summary="List all available prompts",
    response_description="A list of all available system prompts and their categories.",
)
async def list_prompts():
    """
    List all available system prompts.
    
    Returns a list of prompt metadata including name and category.
    Does not return the full content of the prompts to keep the response light.
    """
    service = get_prompt_service()
    return service.list_prompts()

@router.get(
    "/{name}",
    summary="Get prompt content",
    response_description="The full content of the requested system prompt.",
)
async def get_prompt(
    name: str,
):
    """
    Get the full content of a specific system prompt.
    
    Args:
        name: The name of the prompt (folder name), e.g., 'create_coding_project'
    """
    service = get_prompt_service()
    content = service.get_prompt(name)
    
    if content is None:
        raise HTTPException(
            status_code=404,
            detail=f"Prompt '{name}' not found"
        )
        
    return {
        "name": name,
        "content": content
    }

@router.post(
    "/refresh",
    summary="Refresh prompt cache",
    response_description="Confirmation that the cache has been cleared and reloaded.",
)
async def refresh_prompts():
    """
    Force a refresh of the prompt cache.
    Useful if you've added new prompts to the filesystem without restarting the server.
    """
    service = get_prompt_service()
    service.refresh()
    return {"message": "Prompt cache refreshed successfully"}
