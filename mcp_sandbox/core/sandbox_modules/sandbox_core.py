import hashlib
import json
import shutil
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any, Tuple

import docker
from docker.errors import DockerException, ImageNotFound, ContainerError, APIError

from mcp_sandbox.utils.config import logger, DEFAULT_DOCKER_IMAGE, OPEN_MOUNT_DIRECTORY, DEFAULT_CONTAINER_WORK_DIR, \
    DEFAULT_LOG_FILE, config
from mcp_sandbox.utils.exceptions import (
    ExceptionHandler, DockerError, handle_exceptions, safe_execute
)
from mcp_sandbox.utils.logging_config import get_logger


class SandboxManager:
    """沙盒管理器 - 负责Docker容器的创建、管理和清理
    
    提供线程安全的沙盒操作，包括容器生命周期管理、资源跟踪和错误处理。
    """

    def __init__(self, base_image: str = DEFAULT_DOCKER_IMAGE):
        """初始化沙盒管理器
        
        Args:
            base_image: 基础Docker镜像名称
            
        Raises:
            DockerError: Docker客户端初始化失败
            RuntimeError: 沙盒管理器初始化失败
        """
        self.base_image = base_image
        self._lock = threading.RLock()  # 线程安全锁
        self.exception_handler = ExceptionHandler("sandbox_manager")
        self.logger = get_logger("sandbox_manager", use_structured_format=True, log_file=DEFAULT_LOG_FILE)

        # 容器跟踪数据
        self.sandbox_last_used: Dict[str, datetime] = {}
        self.session_sandbox_map: Dict[str, str] = {}
        self.package_install_status: Dict[str, Dict[str, Any]] = {}

        # 初始化Docker客户端
        self._init_docker_client()

        # 确保镜像存在
        self._ensure_sandbox_image()

        # 检查是否需要重置所有容器
        if config["server"].get("reset_all_containers", False):
            self.logger.info("配置指定重置所有容器，正在执行重置操作...")
            self._reset_all_containers()
            self.logger.info("所有容器已重置完成")

        # 加载现有沙盒记录
        self._load_sandbox_records()
        self.logger.info(
            f"沙盒管理器初始化完成，使用镜像: {self.base_image}",
            extra={"base_image": self.base_image, "initialization": "complete"}
        )

    def _cleanup_failed_container(self, container, container_name: str) -> None:
        """清理创建失败的容器
        
        Args:
            container: Docker容器对象（可能为None）
            container_name: 容器名称
        """
        if container is not None:
            try:
                container.remove(force=True)
                self.logger.info(
                    f"已清理失败的容器: {container_name}",
                    extra={"container_name": container_name, "action": "cleanup"}
                )
            except Exception as cleanup_error:
                self.logger.error(
                    f"清理失败容器时出错: {cleanup_error}",
                    extra={"container_name": container_name, "error": str(cleanup_error)},
                    exc_info=True
                )

    @handle_exceptions(reraise=True, audit_action="init_docker_client")
    def _init_docker_client(self) -> None:
        """初始化Docker客户端
        
        Raises:
            DockerError: Docker客户端初始化失败
        """
        try:
            self.sandbox_client = docker.from_env()
            # 测试连接
            self.sandbox_client.ping()
            self.logger.info(
                "Docker客户端初始化成功",
                extra={"docker_version": self.sandbox_client.version().get("Version", "unknown")}
            )
        except DockerException as e:
            docker_error = self.exception_handler.handle_docker_error(
                e, {"operation": "docker_client_init"}
            )
            raise docker_error
        except Exception as e:
            self.logger.error(f"Docker连接测试失败: {e}", exc_info=True)
            raise DockerError(
                message=f"Docker连接失败: {e}",
                details={"operation": "docker_client_init", "error_type": type(e).__name__}
            )

    @handle_exceptions(reraise=True, audit_action="ensure_sandbox_image")
    def _ensure_sandbox_image(self) -> None:
        """确保沙盒镜像存在，如果需要则构建
        
        检查自定义镜像是否存在，如果不存在或Dockerfile有变化则重新构建。
        
        Raises:
            DockerError: 镜像构建失败
        """
        custom_image_name = DEFAULT_DOCKER_IMAGE
        dockerfile_path = Path(config["docker"].get("dockerfile_path", "Dockerfile")).resolve()
        build_info_file = Path(config["docker"].get("build_info_file", ".docker_build_info")).resolve()
        check_changes = config["docker"].get("check_dockerfile_changes", True)

        # 检查镜像是否存在
        image_exists = self._check_image_exists(custom_image_name)
        need_rebuild = not image_exists

        # 如果镜像存在且需要检查变化，比较Dockerfile哈希值
        if image_exists and check_changes and dockerfile_path.exists():
            need_rebuild = self._should_rebuild_image(dockerfile_path, build_info_file)

        # 如果需要重建镜像
        if need_rebuild:
            self._build_sandbox_image(custom_image_name, dockerfile_path, build_info_file, check_changes)

    @handle_exceptions(reraise=True, audit_action="check_image_exists")
    def _check_image_exists(self, image_name: str) -> bool:
        """检查Docker镜像是否存在
        
        Args:
            image_name: 镜像名称
            
        Returns:
            镜像是否存在
        """

        def _check_image():
            self.sandbox_client.images.get(image_name)
            self.logger.info(
                f"沙盒镜像已存在: {image_name}",
                extra={"image_name": image_name, "exists": True}
            )
            return True

        result = safe_execute(
            _check_image,
            default_return=False,
            exception_types=(ImageNotFound, DockerException),
            log_errors=False,
            context={"image_name": image_name, "operation": "check_existence"}
        )

        if not result:
            self.logger.info(
                f"沙盒镜像不存在: {image_name}",
                extra={"image_name": image_name, "exists": False}
            )

        return result

    def _should_rebuild_image(self, dockerfile_path: Path, build_info_file: Path) -> bool:
        """检查是否需要重建镜像
        
        Args:
            dockerfile_path: Dockerfile路径
            build_info_file: 构建信息文件路径
            
        Returns:
            是否需要重建
        """
        current_hash = self._get_file_hash(dockerfile_path)
        previous_hash = self._get_previous_build_hash(build_info_file)

        if previous_hash != current_hash:
            logger.info(f"Dockerfile已变化 (之前: {previous_hash}, 当前: {current_hash})")
            return True
        return False

    @staticmethod
    def _get_previous_build_hash(build_info_file: Path) -> Optional[str]:
        """获取之前构建的哈希值
        
        Args:
            build_info_file: 构建信息文件路径
            
        Returns:
            之前的哈希值，如果不存在则返回None
        """
        if not build_info_file.exists():
            return None

        try:
            with open(build_info_file, 'r', encoding='utf-8') as f:
                build_info = json.load(f)
                previous_hash = build_info.get('dockerfile_hash')
                logger.info(f"找到之前的构建信息，哈希值: {previous_hash}")
                return previous_hash
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"无法读取构建信息文件: {e}")
            return None

    def _build_sandbox_image(self, image_name: str, dockerfile_path: Path,
                             build_info_file: Path, save_build_info: bool) -> None:
        """构建沙盒镜像
        
        Args:
            image_name: 镜像名称
            dockerfile_path: Dockerfile路径
            build_info_file: 构建信息文件路径
            save_build_info: 是否保存构建信息
            
        Raises:
            DockerException: 镜像构建失败
        """
        if not dockerfile_path.exists():
            logger.error(f"Dockerfile不存在: {dockerfile_path}，使用基础镜像")
            return

        try:
            logger.info(f"开始构建沙盒镜像: {image_name}")

            # 构建镜像
            _, logs = self.sandbox_client.images.build(
                path=str(dockerfile_path.parent),
                dockerfile=str(dockerfile_path.name),
                tag=image_name,
                rm=True,
                forcerm=True,
                pull=True  # 确保基础镜像是最新的
            )

            # 输出构建日志
            for log in logs:
                if 'stream' in log:
                    logger.info(log['stream'].strip())
                elif 'error' in log:
                    logger.error(f"构建错误: {log['error']}")

            # 保存构建信息
            if save_build_info:
                self._save_build_info(dockerfile_path, build_info_file, image_name)

            self.base_image = image_name
            logger.info(f"沙盒镜像构建成功: {image_name}")

        except Exception as e:
            logger.error(f"沙盒镜像构建失败: {e}", exc_info=True)
            raise DockerException(f"镜像构建失败: {e}") from e

    def _save_build_info(self, dockerfile_path: Path, build_info_file: Path, image_name: str) -> None:
        """保存构建信息
        
        Args:
            dockerfile_path: Dockerfile路径
            build_info_file: 构建信息文件路径
            image_name: 镜像名称
        """
        try:
            build_info = {
                'dockerfile_hash': self._get_file_hash(dockerfile_path),
                'build_time': datetime.now().isoformat(),
                'image_name': image_name
            }

            with open(build_info_file, 'w', encoding='utf-8') as f:
                json.dump(build_info, f, indent=2, ensure_ascii=False)

            logger.info(f"构建信息已保存到: {build_info_file}")
        except Exception as e:
            logger.warning(f"保存构建信息失败: {e}")

    @staticmethod
    def _get_file_hash(file_path: Path) -> str:
        """计算文件的SHA256哈希值以检测变化
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件的SHA256哈希值，如果文件不存在或读取失败则返回空字符串
        """
        if not file_path.exists():
            logger.warning(f"文件不存在: {file_path}")
            return ""

        try:
            with open(file_path, 'rb') as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()
            logger.debug(f"文件哈希计算完成: {file_path} -> {file_hash[:8]}...")
            return file_hash
        except IOError as e:
            logger.error(f"读取文件进行哈希计算时出错: {e}")
            return ""

    def _reset_all_containers(self) -> None:
        """重置所有Python沙盒容器
        
        删除所有沙盒容器、清理数据库记录和内存状态。
        此操作是线程安全的。
        
        Raises:
            DockerException: Docker操作失败
            DatabaseError: 数据库操作失败
        """
        with self._lock:
            try:
                # 获取所有带有python-sandbox标签的容器
                containers = self.sandbox_client.containers.list(
                    all=True,
                    filters={"label": "python-sandbox"}
                )
                logger.info(f"找到 {len(containers)} 个沙盒容器需要重置")

                # 删除所有容器
                failed_containers = []
                for container in containers:
                    try:
                        self._remove_container_safely(container)
                    except Exception as e:
                        failed_containers.append((container.name, str(e)))
                        logger.error(f"删除容器 {container.name} 失败: {e}", exc_info=True)

                # 清空内存中的记录
                self._clear_memory_state()

                if failed_containers:
                    logger.warning(f"部分容器删除失败: {failed_containers}")
                else:
                    logger.info("所有沙盒容器和记录已成功重置")

            except DockerException as e:
                logger.error(f"Docker操作失败: {e}", exc_info=True)
                raise
            except Exception as e:
                logger.error(f"重置所有容器时出错: {e}", exc_info=True)
                raise DockerException(f"容器重置失败: {e}") from e

    def _remove_container_safely(self, container) -> None:
        """安全地删除单个容器
        
        Args:
            container: Docker容器对象
            
        Raises:
            DockerException: 容器删除失败
        """
        container_id = container.id
        container_name = container.name

        try:
            # 如果容器正在运行，先停止
            if container.status == "running":
                logger.info(f"停止容器 {container_name} ({container_id[:12]})")
                container.stop(timeout=10)  # 给容器10秒时间优雅停止

            # 删除容器
            logger.info(f"删除容器 {container_name} ({container_id[:12]})")
            container.remove(force=True)

            # 清理容器对应的数据目录
            container_data_dir = Path('data') / container_name
            if container_data_dir.exists():
                shutil.rmtree(container_data_dir)
                self.logger.info(
                    f"清理容器数据目录: {container_data_dir}",
                    extra={"container_name": container_name, "data_dir": str(container_data_dir)}
                )


        except Exception as e:
            raise DockerException(f"删除容器 {container_name} 失败: {e}") from e

    def _clear_database_records(self) -> None:
        """清理数据库中的沙盒记录
        
        Raises:
            DatabaseError: 数据库操作失败
        """
        pass

    def _clear_memory_state(self) -> None:
        """清空内存中的状态记录"""
        try:
            # 记录清理前的状态
            last_used_count = len(self.sandbox_last_used)
            session_map_count = len(self.session_sandbox_map)
            package_status_count = len(self.package_install_status)

            # 清空所有状态记录
            self.sandbox_last_used.clear()
            self.session_sandbox_map.clear()
            self.package_install_status.clear()

            logger.info(
                f"内存状态已清空: {last_used_count} 个最后使用记录, "
                f"{session_map_count} 个会话映射, "
                f"{package_status_count} 个包安装状态"
            )
        except Exception as e:
            logger.error(f"清空内存状态时出错: {e}", exc_info=True)

    def _load_sandbox_records(self) -> None:
        """加载现有沙盒记录"""
        try:
            # 获取所有带有python-sandbox标签的容器
            containers = self.sandbox_client.containers.list(
                all=True,
                filters={"label": "python-sandbox"}
            )

            # 更新内存中的记录
            for container in containers:
                self.sandbox_last_used[container.id] = datetime.now()

            logger.info(f"已加载 {len(containers)} 个现有沙盒记录")
        except Exception as e:
            logger.error(f"加载沙盒记录时出错: {e}", exc_info=True)

    def create_sandbox(self, sandbox_name: Optional[str] = None) -> dict:
        """创建新的Docker沙盒容器并返回其ID

        创建一个新的Python沙盒容器，配置资源限制和安全设置。

        Returns:
            str: 新创建的容器ID

        Raises:
            DockerError: 容器创建失败
            ImageNotFound: 沙盒镜像不存在
        """
        # 验证镜像是否存在
        try:
            self.sandbox_client.images.get(self.base_image)
        except ImageNotFound:
            logger.error(f"沙盒镜像 {self.base_image} 不存在")
            raise ImageNotFound(f"沙盒镜像 {self.base_image} 不存在")

        # 生成唯一的容器名称
        sandbox_name = f"python-sandbox-{sandbox_name}"

        try:
            # 创建容器配置

            # 配置容器
            container_config = {
                "image": self.base_image,
                "name": sandbox_name,
                "detach": True,
                "working_dir": DEFAULT_CONTAINER_WORK_DIR,
                "labels": {"python-sandbox": "true"},
                "mem_limit": '1g',
                "memswap_limit": '1g',
                "network_mode": 'bridge',
                "privileged": False,
                "cap_drop": ['ALL'],
                "security_opt": ['no-new-privileges'],
                "read_only": False,  # 允许写入
                "cpu_quota": 50000,  # 限制CPU使用（50%）
                "cpu_period": 100000,  # CPU调度周期

            }

            if OPEN_MOUNT_DIRECTORY:
                # 为每个容器创建唯一的数据目录
                container_data_dir = Path('data') / sandbox_name
                container_data_dir.mkdir(parents=True, exist_ok=True)

                # 挂载容器专属数据目录
                container_config["volumes"] = {
                    str(container_data_dir.absolute()): {
                        'bind': DEFAULT_CONTAINER_WORK_DIR,  # 使用配置文件中的 container_work_dir
                        'mode': 'rw'
                    }
                }

            self.logger.info(
                f"开始创建沙盒容器: {sandbox_name}",
                extra={
                    "sandbox_name": sandbox_name,
                    "base_image": self.base_image,
                    "operation": "create_container"
                }
            )

            # 创建容器
            sandbox = self.sandbox_client.containers.create(**container_config)

            # 启动容器
            sandbox.start()

            docker_container_id = sandbox.id
            current_time = datetime.now()

            # 记录容器使用时间（线程安全）
            with self._lock:
                self.sandbox_last_used[docker_container_id] = current_time

            self.logger.info(
                f"沙盒容器创建成功: {sandbox_name} ({docker_container_id[:12]})",
                extra={
                    "sandbox_name": sandbox_name,
                    "container_id": docker_container_id,
                    "creation_time": current_time.isoformat()
                }
            )
            return {
                "sandbox_id": docker_container_id,
                "sandbox_name": sandbox_name,
                "name": sandbox_name,
                "status": "active"
            }
        except ImageNotFound:
            raise
        except (ContainerError, APIError, DockerException) as e:
            docker_error = self.exception_handler.handle_docker_error(
                e, {
                    "operation": "create_container",
                    "sandbox_name": sandbox_name,
                    "base_image": self.base_image
                }
            )
            raise docker_error
        except Exception as e:
            self.logger.error(
                f"创建沙盒容器失败: {e}",
                extra={"sandbox_name": sandbox_name, "base_image": self.base_image},
                exc_info=True
            )
            raise DockerError(
                message=f"创建沙盒容器失败: {e}",
                details={"sandbox_name": sandbox_name, "base_image": self.base_image}
            ) from e

    def get_container_by_sandbox_id_or_name(self, sandbox_id_or_name: str):
        """通过沙盒ID获取容器

        Args:
            sandbox_id_or_name: 沙盒ID或名称

        Returns:
            tuple: (container, error) - 容器对象和错误信息

        Raises:
            ValueError: 沙盒ID或名称无效
            DatabaseError: 数据库查询失败
            DockerException: Docker操作失败
        """
        # 验证沙盒ID或名称
        if not sandbox_id_or_name:
            error_msg = "沙盒ID或名称不能为空"
            logger.warning(f"[get_container_by_sandbox_id_or_name] {error_msg}")
            return None, {"error": True, "message": error_msg}

        try:
            # 获取Docker容器
            try:
                logger.debug(
                    f"[get_container_by_sandbox_id_or_name] Getting container {sandbox_id_or_name} for sandbox {sandbox_id_or_name}")
                container = self.sandbox_client.containers.get(sandbox_id_or_name)

                # 更新最后使用时间（线程安全）
                with self._lock:
                    self.sandbox_last_used[container.id] = datetime.now()

                logger.debug(f"成功获取容器: {sandbox_id_or_name} (沙盒: {container.id})")
                return container, None

            except docker.errors.NotFound:
                logger.error(
                    f"[get_container_by_sandbox_id] Container {sandbox_id_or_name} not found for sandbox {sandbox_id_or_name}")
                return None, {"error": True,
                              "message": f"容器 {sandbox_id_or_name} 不存在 (沙盒: {sandbox_id_or_name})"}
            except docker.errors.APIError as e:
                logger.error(f"[get_container_by_sandbox_id] Docker API error for sandbox {sandbox_id_or_name}: {e}")
                return None, {"error": True, "message": f"Docker API错误: {e}"}

        except Exception as e:
            logger.error(f"[get_container_by_sandbox_id] Error getting container for sandbox {sandbox_id_or_name}: {e}",
                         exc_info=True)
            return None, {"error": True, "message": f"获取容器失败: {e}"}

    def verify_sandbox_exists(self, sandbox_id: str) -> Optional[Dict[str, Any]]:
        """验证沙盒是否存在

        检查沙盒在数据库和Docker中是否都存在。

        Args:
            sandbox_id: 沙盒ID

        Returns:
            Optional[Dict[str, Any]]: 如果沙盒不存在或有错误，返回错误信息；否则返回None
        """
        if not sandbox_id or not isinstance(sandbox_id, str):
            logger.warning(f"无效的沙盒ID: {sandbox_id}")
            return {"error": True, "message": "无效的沙盒ID"}

        try:

            # 检查Docker容器是否存在
            container, error = self.get_container_by_sandbox_id_or_name(sandbox_id)
            if error:
                logger.debug(f"沙盒 {sandbox_id} 对应的容器不存在或有错误")
                return error

            logger.debug(f"沙盒 {sandbox_id} 验证通过")
            return None

        except Exception as e:
            logger.error(f"验证沙盒存在性失败: {e}", exc_info=True)
            return {"error": True, "message": f"验证沙盒失败: {e}"}

    @handle_exceptions(reraise=False, audit_action="delete_sandbox")
    def delete_sandbox_by_id_or_name(self, sandbox_id_or_name: str) -> bool:
        """删除沙盒容器

        Args:
            sandbox_id_or_name: 沙盒ID或名称

        Returns:
            bool: 删除是否成功
        """
        with self._lock:
            container_deleted = False
            db_deleted = False

            try:
                # 从Docker中删除容器
                try:
                    container = self.sandbox_client.containers.get(sandbox_id_or_name)
                    container.stop(timeout=10)
                    container.remove()
                    container_deleted = True
                    self.logger.info(
                        f"容器 {sandbox_id_or_name[:12]} 已删除",
                        extra={"sandbox_id": sandbox_id_or_name, "action": "container_deleted"}
                    )
                except docker.errors.NotFound:
                    container_deleted = True  # 容器不存在也算删除成功
                    self.logger.warning(
                        f"容器 {sandbox_id_or_name[:12]} 不存在",
                        extra={"sandbox_id": sandbox_id_or_name, "action": "container_not_found"}
                    )
                except DockerException as e:
                    docker_error = self.exception_handler.handle_docker_error(
                        e, {"operation": "delete_container", "sandbox_id": sandbox_id_or_name}
                    )
                    self.logger.error(
                        f"删除容器 {sandbox_id_or_name[:12]} 失败: {docker_error}",
                        extra={"sandbox_id": sandbox_id_or_name, "error": str(docker_error)}
                    )

                # 清理内存跟踪
                self.sandbox_last_used.pop(sandbox_id_or_name, None)

                # 清理会话映射
                sessions_to_remove = [
                    session_id for session_id, sid in self.session_sandbox_map.items()
                    if sid == sandbox_id_or_name
                ]
                for session_id in sessions_to_remove:
                    del self.session_sandbox_map[session_id]

                success = container_deleted
                if success:
                    self.logger.info(
                        f"沙盒 {sandbox_id_or_name} 删除完成",
                        extra={
                            "sandbox_id": sandbox_id_or_name,
                            "container_deleted": container_deleted,
                            "db_deleted": db_deleted
                        }
                    )

                return success

            except Exception as e:
                self.logger.error(
                    f"删除沙盒 {sandbox_id_or_name} 时遇到未知错误: {e}",
                    extra={"sandbox_id": sandbox_id_or_name, "error_type": type(e).__name__},
                    exc_info=True
                )
                return False

    @handle_exceptions(reraise=False, audit_action="get_sandbox_info")
    def get_sandbox_info(self, sandbox_id: str) -> Optional[Dict[str, Any]]:
        """获取沙盒信息

        Args:
            sandbox_id: 沙盒ID

        Returns:
            Optional[Dict[str, Any]]: 沙盒信息，如果不存在返回None
        """
        try:
            container = self.sandbox_client.containers.get(sandbox_id)
            container_status = container.status
            container_info = {
                "id": container.id,
                "name": container.name,
                "status": container_status,
                "created": container.attrs.get("Created"),
                "image": container.image.tags[0] if container.image.tags else "unknown"
            }
            self.logger.debug(
                f"获取容器信息成功: {sandbox_id[:12]}",
                extra={"sandbox_id": sandbox_id, "container_status": container_status}
            )

            result = {
                "sandbox_id": sandbox_id,
                "last_used": self.sandbox_last_used.get(sandbox_id),
                "container_status": container_status,
                "container_info": container_info
            }

            self.logger.debug(
                f"沙盒信息获取成功: {sandbox_id}",
                extra={"sandbox_id": sandbox_id, "has_container_info": container_info is not None}
            )

            return result
        except docker.errors.NotFound:
            self.logger.warning(
                f"容器不存在: {sandbox_id[:12]}",
                extra={"sandbox_id": sandbox_id, "container_status": "not_found"}
            )
        except DockerException as e:
            docker_error = self.exception_handler.handle_docker_error(
                e, {"operation": "get_container_info", "sandbox_id": sandbox_id}
            )
            self.logger.warning(
                f"获取容器信息失败: {docker_error}",
                extra={"sandbox_id": sandbox_id, "error": str(docker_error)}
            )


        except Exception as e:
            self.logger.error(
                f"获取沙盒信息失败: {e}",
                extra={"sandbox_id": sandbox_id, "error_type": type(e).__name__},
                exc_info=True
            )
            return None

    @contextmanager
    def get_running_sandbox(self, sandbox_id: str):
        """获取运行中的沙盒容器

        Args:
            sandbox_id: 沙盒ID

        Yields:
            Container: 运行中的Docker容器对象

        Raises:
            ValueError: 沙盒不存在或无法启动
            DockerException: Docker操作失败
        """
        if not sandbox_id or not isinstance(sandbox_id, str):
            raise ValueError("沙盒ID不能为空且必须是字符串")

        container, error = self.get_container_by_sandbox_id_or_name(sandbox_id)
        if error:
            logger.error(f"Failed to get container for sandbox {sandbox_id}: {error['message']}")
            raise ValueError(error["message"])

        try:
            # 刷新容器状态
            container.reload()

            # 确保容器正在运行
            if container.status != "running":
                logger.info(f"Sandbox {sandbox_id} container is not running. Current status: {container.status}")

                # 如果容器已退出，尝试获取日志以了解原因
                if container.status == "exited":
                    try:
                        logs = container.logs(tail=50).decode('utf-8')
                        logger.info(f"Logs from exited container for sandbox {sandbox_id}:\n{logs}")
                    except Exception as log_err:
                        logger.error(f"Failed to get logs for exited sandbox {sandbox_id}: {log_err}")

                # 尝试启动容器
                logger.info(f"Attempting to start container for sandbox {sandbox_id}...")
                try:
                    container.start()
                    container.reload()
                    logger.info(f"Container for sandbox {sandbox_id} started successfully.")
                except Exception as start_err:
                    logger.error(f"Failed to start container for sandbox {sandbox_id}: {start_err}")
                    raise DockerException(f"无法启动沙盒容器: {start_err}") from start_err

            # 更新最后使用时间
            with self._lock:
                self.sandbox_last_used[container.id] = datetime.now()

            yield container

        except Exception as e:
            logger.error(f"Error in _get_running_sandbox for {sandbox_id}: {e}", exc_info=True)
            raise
