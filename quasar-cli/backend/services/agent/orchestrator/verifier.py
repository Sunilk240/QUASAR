"""
Result Verification Module

Verifies tool results before considering task complete.
Provides self-correction capabilities for the agent.
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import re

from ..logger import agent_logger


class VerificationStatus(Enum):
    """Status of verification result."""
    PASSED = "passed"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"
    SKIPPED = "skipped"


@dataclass
class VerificationResult:
    """Result of a verification check."""
    status: VerificationStatus
    message: str
    details: Optional[Dict[str, Any]] = None
    suggested_fix: Optional[str] = None


class Verifier:
    """
    Verifies that tool actions achieved their intended effect.
    
    Provides automatic verification for:
    - File creation and content
    - Syntax validation
    - Command execution
    - Test generation
    """
    
    def __init__(self, workspace: Path):
        """
        Initialize verifier.
        
        Args:
            workspace: Path to workspace directory
        """
        self.workspace = Path(workspace)
        agent_logger.debug(f"Verifier initialized for workspace: {workspace}")
    
    async def verify_file_created(
        self,
        path: str,
        expected_content_patterns: Optional[List[str]] = None
    ) -> VerificationResult:
        """
        Verify file was created with expected content.
        
        Args:
            path: File path relative to workspace
            expected_content_patterns: Optional patterns to check for
            
        Returns:
            VerificationResult with status and details
        """
        full_path = self.workspace / path
        
        # Check if file exists
        if not full_path.exists():
            agent_logger.warning(f"Verification failed: File not found: {path}")
            return VerificationResult(
                status=VerificationStatus.FAILED,
                message=f"File not found: {path}",
                suggested_fix="Check the path and try creating again"
            )
        
        # Check if it's actually a file
        if not full_path.is_file():
            agent_logger.warning(f"Verification failed: Not a file: {path}")
            return VerificationResult(
                status=VerificationStatus.FAILED,
                message=f"Path exists but is not a file: {path}",
                suggested_fix="Use a different path"
            )
        
        try:
            content = full_path.read_text(encoding='utf-8')
        except Exception as e:
            agent_logger.error(f"Verification error reading file: {e}")
            return VerificationResult(
                status=VerificationStatus.FAILED,
                message=f"Could not read file: {str(e)}",
                suggested_fix="Check file permissions"
            )
        
        # Check for expected patterns
        if expected_content_patterns:
            missing = []
            for pattern in expected_content_patterns:
                if pattern not in content:
                    missing.append(pattern)
            
            if missing:
                agent_logger.warning(f"Verification: Missing expected patterns in {path}")
                return VerificationResult(
                    status=VerificationStatus.NEEDS_REVIEW,
                    message=f"File created but missing expected content",
                    details={"missing_patterns": missing},
                    suggested_fix="Add the missing content to the file"
                )
        
        # Success
        lines = len(content.splitlines())
        agent_logger.debug(f"Verification passed: {path} ({lines} lines)")
        return VerificationResult(
            status=VerificationStatus.PASSED,
            message=f"File created successfully: {path}",
            details={"lines": lines, "size_bytes": len(content)}
        )
    
    async def verify_syntax(
        self,
        path: str,
        language: str
    ) -> VerificationResult:
        """
        Verify file has valid syntax.
        
        Args:
            path: File path relative to workspace
            language: Programming language (python, json, etc.)
            
        Returns:
            VerificationResult with syntax check status
        """
        full_path = self.workspace / path
        
        if not full_path.exists():
            return VerificationResult(
                status=VerificationStatus.FAILED,
                message=f"File not found: {path}"
            )
        
        try:
            content = full_path.read_text(encoding='utf-8')
        except Exception as e:
            return VerificationResult(
                status=VerificationStatus.FAILED,
                message=f"Could not read file: {str(e)}"
            )
        
        # Python syntax check
        if language == "python":
            try:
                import ast
                ast.parse(content)
                agent_logger.debug(f"Python syntax valid: {path}")
                return VerificationResult(
                    status=VerificationStatus.PASSED,
                    message="Python syntax is valid"
                )
            except SyntaxError as e:
                agent_logger.warning(f"Python syntax error in {path}: line {e.lineno}")
                return VerificationResult(
                    status=VerificationStatus.FAILED,
                    message=f"Syntax error at line {e.lineno}: {e.msg}",
                    details={"line": e.lineno, "offset": e.offset},
                    suggested_fix=f"Fix the syntax error on line {e.lineno}"
                )
        
        # JSON syntax check
        elif language == "json":
            try:
                import json
                json.loads(content)
                agent_logger.debug(f"JSON syntax valid: {path}")
                return VerificationResult(
                    status=VerificationStatus.PASSED,
                    message="JSON is valid"
                )
            except json.JSONDecodeError as e:
                agent_logger.warning(f"JSON syntax error in {path}: {e.msg}")
                return VerificationResult(
                    status=VerificationStatus.FAILED,
                    message=f"Invalid JSON: {e.msg}",
                    details={"line": e.lineno, "column": e.colno},
                    suggested_fix="Fix the JSON syntax"
                )
        
        # YAML syntax check
        elif language in ["yaml", "yml"]:
            try:
                import yaml
                yaml.safe_load(content)
                agent_logger.debug(f"YAML syntax valid: {path}")
                return VerificationResult(
                    status=VerificationStatus.PASSED,
                    message="YAML is valid"
                )
            except yaml.YAMLError as e:
                agent_logger.warning(f"YAML syntax error in {path}")
                return VerificationResult(
                    status=VerificationStatus.FAILED,
                    message=f"Invalid YAML: {str(e)}",
                    suggested_fix="Fix the YAML syntax"
                )
            except ImportError:
                # yaml not installed, skip
                return VerificationResult(
                    status=VerificationStatus.SKIPPED,
                    message="YAML checker not available (pyyaml not installed)"
                )
        
        # No checker available for this language
        return VerificationResult(
            status=VerificationStatus.SKIPPED,
            message=f"No syntax checker available for {language}"
        )
    
    async def verify_command_success(
        self,
        command: str,
        result: Dict[str, Any]
    ) -> VerificationResult:
        """
        Verify command executed successfully.
        
        Args:
            command: Command that was executed
            result: Result dictionary from tool execution
            
        Returns:
            VerificationResult with command status
        """
        exit_code = result.get("exit_code", -1)
        output = result.get("output", "")
        
        # Success
        if exit_code == 0:
            agent_logger.debug(f"Command succeeded: {command[:50]}")
            return VerificationResult(
                status=VerificationStatus.PASSED,
                message="Command completed successfully"
            )
        
        # Analyze common errors
        agent_logger.warning(f"Command failed (exit {exit_code}): {command[:50]}")
        
        # Missing Python module
        if "ModuleNotFoundError" in output or "No module named" in output:
            module = self._extract_module_name(output)
            return VerificationResult(
                status=VerificationStatus.FAILED,
                message=f"Missing Python module: {module}",
                details={"module": module, "exit_code": exit_code},
                suggested_fix=f"pip install {module}"
            )
        
        # Permission denied
        if "Permission denied" in output or "PermissionError" in output:
            return VerificationResult(
                status=VerificationStatus.FAILED,
                message="Permission denied",
                details={"exit_code": exit_code},
                suggested_fix="Check file permissions or run with elevated privileges"
            )
        
        # File not found
        if "FileNotFoundError" in output or "No such file" in output:
            return VerificationResult(
                status=VerificationStatus.FAILED,
                message="File or directory not found",
                details={"exit_code": exit_code},
                suggested_fix="Check that the file path is correct"
            )
        
        # Command not found
        if "command not found" in output.lower() or "is not recognized" in output:
            return VerificationResult(
                status=VerificationStatus.FAILED,
                message="Command not found",
                details={"exit_code": exit_code},
                suggested_fix="Install the required command or check PATH"
            )
        
        # Generic failure
        return VerificationResult(
            status=VerificationStatus.FAILED,
            message=f"Command failed with exit code {exit_code}",
            details={"exit_code": exit_code, "output": output[-500:]}  # Last 500 chars
        )
    
    async def verify_test_generation(
        self,
        test_file: str,
        source_file: str
    ) -> VerificationResult:
        """
        Verify generated tests are valid.
        
        Args:
            test_file: Path to test file
            source_file: Path to source file being tested
            
        Returns:
            VerificationResult with test validation status
        """
        # 1. Check test file exists
        create_result = await self.verify_file_created(test_file)
        if create_result.status != VerificationStatus.PASSED:
            return create_result
        
        # 2. Check syntax
        syntax_result = await self.verify_syntax(test_file, "python")
        if syntax_result.status != VerificationStatus.PASSED:
            return syntax_result
        
        # 3. Check that file contains test functions
        full_path = self.workspace / test_file
        content = full_path.read_text(encoding='utf-8')
        
        # Look for test functions (pytest or unittest style)
        test_functions = re.findall(r'def (test_\w+)\(', content)
        test_classes = re.findall(r'class (Test\w+)\(', content)
        
        if not test_functions and not test_classes:
            agent_logger.warning(f"No test functions found in {test_file}")
            return VerificationResult(
                status=VerificationStatus.NEEDS_REVIEW,
                message="Test file created but contains no test functions",
                suggested_fix="Add test functions (def test_*) to the file"
            )
        
        # Success
        test_count = len(test_functions) + len(test_classes)
        agent_logger.debug(f"Test file valid: {test_file} ({test_count} tests)")
        return VerificationResult(
            status=VerificationStatus.PASSED,
            message=f"Test file is valid with {test_count} test(s)",
            details={"test_functions": test_functions, "test_classes": test_classes}
        )
    
    def _extract_module_name(self, output: str) -> str:
        """
        Extract module name from error output.
        
        Args:
            output: Error output containing module name
            
        Returns:
            Module name or "unknown"
        """
        # Try to extract from "No module named 'xxx'"
        match = re.search(r"No module named ['\"]([^'\"]+)['\"]", output)
        if match:
            return match.group(1)
        
        # Try to extract from "ModuleNotFoundError: No module named xxx"
        match = re.search(r"ModuleNotFoundError.*?([a-zA-Z_][a-zA-Z0-9_]*)", output)
        if match:
            return match.group(1)
        
        return "unknown"
