"""
Backup Manager for File Operations

Stores backups in .quasar/backups/ with timestamps.
Provides restore functionality and automatic cleanup.
"""

from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
import shutil
import json
import logging

logger = logging.getLogger("backup_manager")


class BackupManager:
    """
    Manages file backups in .quasar/backups/
    
    Features:
    - Automatic backup before modify/delete
    - Timestamp-based backup IDs
    - Restore functionality
    - Auto-cleanup (keeps last 50 backups)
    - JSON index for tracking
    """
    
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.backup_dir = workspace / ".quasar" / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.backup_dir / "index.json"
        self._load_index()
        logger.info(f"💾 BackupManager initialized: {self.backup_dir}")
    
    def _load_index(self):
        """Load backup index (tracks all backups)."""
        if self.index_file.exists():
            try:
                self.index = json.loads(self.index_file.read_text(encoding='utf-8'))
            except Exception as e:
                logger.error(f"Failed to load backup index: {e}")
                self.index = {"backups": []}
        else:
            self.index = {"backups": []}
    
    def _save_index(self):
        """Save backup index."""
        try:
            self.index_file.write_text(
                json.dumps(self.index, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
        except Exception as e:
            logger.error(f"Failed to save backup index: {e}")
    
    def create_backup(self, file_path: Path, operation: str) -> Optional[str]:
        """
        Create backup before modifying/deleting file.
        
        Args:
            file_path: Path to file being modified
            operation: "modify", "delete", "overwrite"
            
        Returns:
            Backup ID (timestamp-based) or None if failed
        """
        if not file_path.exists():
            logger.debug(f"File doesn't exist, skipping backup: {file_path}")
            return None
        
        try:
            # Generate backup ID
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # milliseconds
            rel_path = file_path.relative_to(self.workspace)
            safe_path = str(rel_path).replace('/', '_').replace('\\', '_')
            backup_id = f"{timestamp}_{safe_path}"
            
            # Create backup file
            backup_path = self.backup_dir / backup_id
            shutil.copy2(file_path, backup_path)
            
            # Record in index
            self.index["backups"].append({
                "id": backup_id,
                "original_path": str(rel_path),
                "timestamp": timestamp,
                "operation": operation,
                "size": file_path.stat().st_size
            })
            
            # Keep only last 50 backups (prevent disk bloat)
            if len(self.index["backups"]) > 50:
                old_backup = self.index["backups"].pop(0)
                old_file = self.backup_dir / old_backup["id"]
                if old_file.exists():
                    old_file.unlink()
                    logger.debug(f"Removed old backup: {old_backup['id']}")
            
            self._save_index()
            logger.info(f"✅ Created backup: {backup_id} for {operation}")
            return backup_id
            
        except Exception as e:
            logger.error(f"Failed to create backup for {file_path}: {e}")
            return None
    
    def restore_backup(self, backup_id: str) -> bool:
        """
        Restore a backup by ID.
        
        Args:
            backup_id: Backup ID from list_backups()
            
        Returns:
            True if restored successfully
        """
        backup_info = next((b for b in self.index["backups"] if b["id"] == backup_id), None)
        if not backup_info:
            logger.error(f"Backup not found: {backup_id}")
            return False
        
        backup_file = self.backup_dir / backup_id
        if not backup_file.exists():
            logger.error(f"Backup file missing: {backup_id}")
            return False
        
        try:
            original_path = self.workspace / backup_info["original_path"]
            original_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_file, original_path)
            logger.info(f"✅ Restored backup: {backup_id} to {backup_info['original_path']}")
            return True
        except Exception as e:
            logger.error(f"Failed to restore backup {backup_id}: {e}")
            return False
    
    def list_backups(self, file_path: Optional[str] = None) -> List[Dict]:
        """
        List all backups, optionally filtered by file.
        
        Args:
            file_path: Optional - filter by specific file
            
        Returns:
            List of backup dictionaries
        """
        if file_path:
            # Normalize path for comparison
            file_path = file_path.replace('\\', '/')
            return [b for b in self.index["backups"] if b["original_path"] == file_path]
        return self.index["backups"]
    
    def get_last_backup(self, file_path: str) -> Optional[Dict]:
        """
        Get most recent backup for a file.
        
        Args:
            file_path: File path to search for
            
        Returns:
            Backup info dict or None
        """
        backups = self.list_backups(file_path)
        return backups[-1] if backups else None
    
    def get_backup_content(self, backup_id: str) -> Optional[str]:
        """
        Read content of a backup file.
        
        Args:
            backup_id: Backup ID
            
        Returns:
            File content or None
        """
        backup_file = self.backup_dir / backup_id
        if not backup_file.exists():
            return None
        
        try:
            return backup_file.read_text(encoding='utf-8')
        except Exception as e:
            logger.error(f"Failed to read backup {backup_id}: {e}")
            return None
