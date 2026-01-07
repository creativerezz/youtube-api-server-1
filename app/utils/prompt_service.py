import os
import logging
from typing import Dict, List, Optional, TypedDict
from functools import lru_cache

from app.core.config import settings

logger = logging.getLogger(__name__)

# Define the structure of a prompt response
class PromptInfo(TypedDict):
    name: str
    category: str
    path: str
    content: Optional[str]

class PromptService:
    """
    Service to manage loading and caching of system prompts.
    
    Prompts are stored in the 'prompts' directory at the project root.
    This service provides methods to list available prompts and retrieve their content.
    """
    
    def __init__(self):
        # Determine the prompts directory relative to the project root
        # Assuming app is in /app, prompts is in /prompts (sibling)
        # Or if running locally: /Users/reza/Github/FastYTProxie/prompts
        
        # We can try to find it relative to this file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Go up two levels: app/utils -> app -> root
        self.prompts_dir = os.path.abspath(os.path.join(current_dir, "../../prompts"))
        
        self._cache: Dict[str, PromptInfo] = {}
        self._loaded = False
        
    def _load_prompts(self) -> None:
        """
        Scan the prompts directory and populate the cache.
        This is called lazily on the first request.
        """
        if self._loaded:
            return

        if not os.path.exists(self.prompts_dir):
            logger.warning(f"Prompts directory not found at {self.prompts_dir}")
            return

        logger.info(f"Loading prompts from {self.prompts_dir}")
        
        count = 0
        for root, dirs, files in os.walk(self.prompts_dir):
            for file in files:
                if file == "system.md":
                    # The parent folder name is the prompt name
                    prompt_name = os.path.basename(root)
                    
                    # The grandparent folder is the category (if any)
                    rel_path = os.path.relpath(root, self.prompts_dir)
                    parts = rel_path.split(os.sep)
                    
                    category = "uncategorized"
                    if len(parts) > 1:
                        category = parts[0]
                        # If nested deeper, we might want to handle that, but for now assume category/prompt_name
                    
                    full_path = os.path.join(root, file)
                    
                    self._cache[prompt_name] = {
                        "name": prompt_name,
                        "category": category,
                        "path": full_path,
                        "content": None # Content loaded on demand
                    }
                    count += 1
        
        self._loaded = True
        logger.info(f"Loaded {count} prompts into cache")

    def list_prompts(self) -> List[PromptInfo]:
        """Return a list of all available prompts (without content)."""
        self._load_prompts()
        # Return a list of dicts without the 'content' field to keep it light
        return [
            {k: v for k, v in p.items() if k != "content"} 
            for p in self._cache.values()
        ]

    def get_prompt(self, name: str) -> Optional[str]:
        """
        Get the content of a specific prompt by name.
        Content is cached in memory after first read.
        """
        self._load_prompts()
        
        if name not in self._cache:
            return None
        
        prompt_info = self._cache[name]
        
        # Load content if not already in memory
        if prompt_info["content"] is None:
            try:
                with open(prompt_info["path"], "r", encoding="utf-8") as f:
                    prompt_info["content"] = f.read()
            except Exception as e:
                logger.error(f"Error reading prompt file {prompt_info['path']}: {e}")
                return None
                
        return prompt_info["content"]

    def refresh(self) -> None:
        """Clear cache and reload prompts from disk."""
        self._cache = {}
        self._loaded = False
        self._load_prompts()

# Singleton instance
_prompt_service = PromptService()

def get_prompt_service() -> PromptService:
    return _prompt_service
