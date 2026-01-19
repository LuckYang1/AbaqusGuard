"""
飞书多维表格 API 客户端
提供创建、更新、查询记录等基础功能
"""

import lark_oapi as lark
from lark_oapi.api.bitable.v1 import (
    CreateAppTableRecordRequest,
    UpdateAppTableRecordRequest,
    SearchAppTableRecordRequest,
    SearchAppTableRecordRequestBody,
    GetAppTableRecordRequest,
    DeleteAppTableRecordRequest,
    AppTableRecord,
)
from typing import Optional, Dict, Any, List


class BitableClient:
    """飞书多维表格客户端"""

    def __init__(self, app_id: str, app_secret: str, verbose: bool = False):
        """
        初始化客户端

        Args:
            app_id: 飞书应用 ID
            app_secret: 飞书应用 Secret
            verbose: 是否输出详细日志
        """
        log_level = lark.LogLevel.DEBUG if verbose else lark.LogLevel.INFO
        self.client = (
            lark.Client.builder()
            .app_id(app_id)
            .app_secret(app_secret)
            .log_level(log_level)
            .build()
        )
        self.verbose = verbose

    def _log(self, message: str):
        """输出日志"""
        if self.verbose:
            print(f"[BitableClient] {message}")

    def create_record(
        self, app_token: str, table_id: str, fields: Dict[str, Any]
    ) -> Optional[str]:
        """
        创建记录

        Args:
            app_token: 多维表格 token
            table_id: 数据表 ID
            fields: 字段数据

        Returns:
            记录 ID，失败返回 None
        """
        try:
            # 构建记录对象
            record = AppTableRecord.builder().fields(fields).build()

            # 构建请求对象
            request = (
                CreateAppTableRecordRequest.builder()
                .app_token(app_token)
                .table_id(table_id)
                .request_body(record)
                .build()
            )

            # 发送请求
            response = self.client.bitable.v1.app_table_record.create(request)

            if not response.success():
                self._log(
                    f"创建记录失败: code={response.code}, msg={response.msg}, "
                    f"log_id={response.get_log_id()}"
                )
                return None

            # 获取记录 ID
            record_id = response.data.record.record_id
            self._log(f"创建记录成功: record_id={record_id}")
            return record_id

        except Exception as e:
            self._log(f"创建记录异常: {e}")
            return None

    def update_record(
        self, app_token: str, table_id: str, record_id: str, fields: Dict[str, Any]
    ) -> bool:
        """
        更新记录

        Args:
            app_token: 多维表格 token
            table_id: 数据表 ID
            record_id: 记录 ID
            fields: 要更新的字段数据

        Returns:
            是否成功
        """
        try:
            # 构建记录对象
            record = AppTableRecord.builder().fields(fields).build()

            # 构建请求对象
            request = (
                UpdateAppTableRecordRequest.builder()
                .app_token(app_token)
                .table_id(table_id)
                .record_id(record_id)
                .request_body(record)
                .build()
            )

            # 发送请求
            response = self.client.bitable.v1.app_table_record.update(request)

            if not response.success():
                self._log(
                    f"更新记录失败: record_id={record_id}, code={response.code}, "
                    f"msg={response.msg}, log_id={response.get_log_id()}"
                )
                return False

            self._log(f"更新记录成功: record_id={record_id}")
            return True

        except Exception as e:
            self._log(f"更新记录异常: record_id={record_id}, {e}")
            return False

    def search_records(
        self,
        app_token: str,
        table_id: str,
        filter_str: Optional[str] = None,
        field_names: Optional[List[str]] = None,
        page_size: int = 100,
        page_token: str = "",
    ) -> Optional[List[Dict[str, Any]]]:
        """
        查询记录

        Args:
            app_token: 多维表格 token
            table_id: 数据表 ID
            filter_str: 过滤条件（公式格式，如 '([作业名称]="TestJob")'）
            field_names: 要返回的字段列表
            page_size: 每页数量
            page_token: 分页 token

        Returns:
            记录列表，失败返回 None
        """
        try:
            # 构建请求体
            body_builder = SearchAppTableRecordRequestBody.builder()

            if field_names:
                body_builder.field_names(field_names)

            request_body = body_builder.build()

            # 构建请求对象
            request_builder = (
                SearchAppTableRecordRequest.builder()
                .app_token(app_token)
                .table_id(table_id)
                .page_size(page_size)
                .request_body(request_body)
            )

            if page_token:
                request_builder.page_token(page_token)

            request = request_builder.build()

            # 发送请求
            response = self.client.bitable.v1.app_table_record.search(request)

            if not response.success():
                self._log(
                    f"查询记录失败: code={response.code}, msg={response.msg}, "
                    f"log_id={response.get_log_id()}"
                )
                return None

            # 转换记录为字典列表
            records = response.data.items or []
            result = []
            for item in records:
                result.append(
                    {
                        "record_id": item.record_id,
                        "fields": item.fields if hasattr(item, "fields") else {},
                    }
                )

            self._log(f"查询记录成功: 找到 {len(result)} 条记录")
            return result

        except Exception as e:
            self._log(f"查询记录异常: {e}")
            return None

    def get_record(
        self, app_token: str, table_id: str, record_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        获取单条记录

        Args:
            app_token: 多维表格 token
            table_id: 数据表 ID
            record_id: 记录 ID

        Returns:
            记录数据，失败返回 None
        """
        try:
            # 构建请求对象
            request = (
                GetAppTableRecordRequest.builder()
                .app_token(app_token)
                .table_id(table_id)
                .record_id(record_id)
                .build()
            )

            # 发送请求
            response = self.client.bitable.v1.app_table_record.get(request)

            if not response.success():
                self._log(
                    f"获取记录失败: record_id={record_id}, code={response.code}, "
                    f"msg={response.msg}, log_id={response.get_log_id()}"
                )
                return None

            # 转换为字典
            record = response.data.record
            return {
                "record_id": record.record_id,
                "fields": record.fields if hasattr(record, "fields") else {},
            }

        except Exception as e:
            self._log(f"获取记录异常: record_id={record_id}, {e}")
            return None

    def delete_record(self, app_token: str, table_id: str, record_id: str) -> bool:
        """
        删除记录

        Args:
            app_token: 多维表格 token
            table_id: 数据表 ID
            record_id: 记录 ID

        Returns:
            是否成功
        """
        try:
            # 构建请求对象
            request = (
                DeleteAppTableRecordRequest.builder()
                .app_token(app_token)
                .table_id(table_id)
                .record_id(record_id)
                .build()
            )

            # 发送请求
            response = self.client.bitable.v1.app_table_record.delete(request)

            if not response.success():
                self._log(
                    f"删除记录失败: record_id={record_id}, code={response.code}, "
                    f"msg={response.msg}, log_id={response.get_log_id()}"
                )
                return False

            self._log(f"删除记录成功: record_id={record_id}")
            return True

        except Exception as e:
            self._log(f"删除记录异常: record_id={record_id}, {e}")
            return False
