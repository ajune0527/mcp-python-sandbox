from typing import List, Optional
from pydantic import BaseModel

class FileLink(BaseModel):
    """文件链接模型"""
    name: str  # 文件名
    url: str   # 文件URL

class CodeExecutionResponse(BaseModel):
    """代码执行响应模型"""
    stdout: str                      # 标准输出
    stderr: str                      # 标准错误
    exit_code: int                   # 退出码
    files: List[str] = []           # 生成的文件列表
    file_links: List[FileLink] = []  # 文件链接列表
    error: Optional[str] = None      # 错误信息（如果有）