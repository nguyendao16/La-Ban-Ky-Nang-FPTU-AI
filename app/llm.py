"""Shared stage settings and a single preflight/generation SDK request."""
from __future__ import annotations
import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
import openai
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError
from scripts.openai_model_config import MODEL_CAPABILITIES
from app.engines.errors import ComparisonError
ROOT = Path(__file__).resolve().parents[1]
MAX_OUTPUT_TOKENS = 4096

@dataclass(frozen=True)
class LLMSettings:
    api_key: str = field(repr=False)
    model: str = "gpt-4o-mini"
    context_window: int | None = None
    temperature: float | None = None
    stage: Literal["review", "chat"] = "review"
    reasoning_effort: str | None = None
    max_output_tokens: int | None = None
    request_timeout: float | None = None

    def __post_init__(self) -> None:
        if self.request_timeout is not None and (type(self.request_timeout) not in (int, float)
                or not math.isfinite(self.request_timeout) or self.request_timeout <= 0):
            raise ComparisonError("Request timeout phải là số hữu hạn lớn hơn 0")
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise ComparisonError("Thiếu OPENAI_API_KEY; cấu hình trong môi trường hoặc .env tại root")
        if not isinstance(self.model, str) or not self.model.strip():
            raise ComparisonError("Tên model không được rỗng")
        if not isinstance(self.stage, str) or self.stage not in {"review", "chat"}:
            raise ComparisonError("Stage phải là review hoặc chat")
        capability = MODEL_CAPABILITIES.get(self.model)
        if capability is None:
            raise ComparisonError("Model/snapshot chưa xác nhận capability; --context-window không thay thế kiểm tra model")
        effort = self.reasoning_effort
        if capability.reasoning_efforts:
            if effort is None:
                effort = "high" if self.stage == "review" else "medium"
            if not isinstance(effort, str) or effort not in capability.reasoning_efforts:
                raise ComparisonError("Reasoning effort không được model hỗ trợ")
        elif effort is not None:
            raise ComparisonError("Model không hỗ trợ reasoning effort; bỏ cấu hình reasoning")
        temperature_allowed = capability.temperature_without_reasoning and effort in {None, "none"}
        if self.temperature is not None and (type(self.temperature) not in (int, float) or not math.isfinite(self.temperature) or not 0 <= self.temperature <= 2):
            raise ComparisonError("Temperature phải là số hữu hạn trong khoảng 0–2")
        if self.temperature is not None and not temperature_allowed:
            raise ComparisonError("Chưa xác nhận model/effort hỗ trợ temperature; bỏ --temperature")
        output = self.max_output_tokens
        if output is None:
            output = (16384 if self.stage == "review" else 8192) if capability.reasoning_efforts else MAX_OUTPUT_TOKENS
        if type(output) is not int or not 16 <= output <= capability.max_output_tokens:
            raise ComparisonError("max-output-tokens phải là số nguyên trong giới hạn output của model")
        limit = capability.context_window if self.context_window is None else self.context_window
        if type(limit) is not int or limit <= output:
            raise ComparisonError(f"--context-window phải là số nguyên lớn hơn {output}")
        if limit > capability.context_window:
            raise ComparisonError("--context-window không được vượt giới hạn model đã xác nhận")
        object.__setattr__(self, "context_window", limit)
        object.__setattr__(self, "reasoning_effort", effort)
        object.__setattr__(self, "max_output_tokens", output)
        if self.temperature is None and temperature_allowed:
            object.__setattr__(self, "temperature", 0.0)

    @property
    def timeout(self) -> float:
        if self.request_timeout is not None:
            return float(self.request_timeout)
        return 180.0 if self.reasoning_effort not in {None, "none"} else 60.0

    @property
    def reasoning_options(self) -> dict[str, Any]:
        return {"reasoning": {"effort": self.reasoning_effort}} if self.reasoning_effort is not None else {}


def load_settings(context_window: int | None = None, *, temperature: float | None = None,
                  stage: Literal["review", "chat"] = "review", model: str | None = None,
                  reasoning_effort: str | None = None, max_output_tokens: int | None = None,
                  request_timeout: float | None = None, api_key: str | None = None) -> LLMSettings:
    if not isinstance(stage, str) or stage not in {"review", "chat"}:
        raise ComparisonError("Stage phải là review hoặc chat")
    load_dotenv(ROOT / ".env", override=False)
    prefix = f"OPENAI_{stage.upper()}_"
    raw_output = os.environ.get(prefix + "MAX_OUTPUT_TOKENS")
    if max_output_tokens is None and raw_output is not None:
        try:
            max_output_tokens = int(raw_output)
        except ValueError as exc:
            raise ComparisonError(f"{prefix}MAX_OUTPUT_TOKENS phải là số nguyên") from exc
    raw_timeout = os.environ.get(prefix + "REQUEST_TIMEOUT")
    if request_timeout is None and raw_timeout is not None:
        try:
            request_timeout = float(raw_timeout)
        except ValueError as exc:
            raise ComparisonError(f"{prefix}REQUEST_TIMEOUT phải là số hữu hạn lớn hơn 0") from exc
    return LLMSettings(
        api_key=os.environ.get("OPENAI_API_KEY", "") if api_key is None else api_key,
        model=model if model is not None else os.environ.get(prefix + "MODEL", os.environ.get("OPENAI_MODEL") or os.environ.get("MODEL") or "gpt-4o-mini"),
        context_window=context_window,
        temperature=temperature,
        stage=stage,
        reasoning_effort=reasoning_effort if reasoning_effort is not None else os.environ.get(prefix + "REASONING_EFFORT"),
        max_output_tokens=max_output_tokens,
        request_timeout=request_timeout,
    )


def structured_schema_format(response_model: type[BaseModel]) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": response_model.__name__,
        "strict": True,
        "schema": response_model.model_json_schema(),
    }


def request_structured_response(
    instructions: str, input_messages: list[dict[str, Any]], response_model: type[BaseModel],
    settings: LLMSettings, *, client: Any | None = None, context_budget: int | None = None,
    operation_label: str = "review", web_search: bool = False,
) -> Any:
    """One preflight and one generation, with the existing SDK failure policy."""
    budget = settings.context_window if context_budget is None else context_budget
    if type(budget) is not int or not settings.max_output_tokens < budget <= settings.context_window:
        raise ComparisonError("Context budget phải lớn hơn output budget và không vượt context model")
    if web_search:
        budget = min(budget, 128000)  # Hosted search has its own context ceiling.
    search_options = ({"tools": [{"type": "web_search", "filters": {"allowed_domains": ["coursera.org"]}}],
                       "tool_choice": "required"} if web_search else {})
    owned_client = client is None
    if owned_client:
        client = openai.OpenAI(api_key=settings.api_key, timeout=settings.timeout, max_retries=0)
    try:
        count = client.responses.input_tokens.count(
            timeout=settings.timeout,
            model=settings.model,
            instructions=instructions,
            input=input_messages,
            text={"format": structured_schema_format(response_model)},
            **settings.reasoning_options,
            **search_options,
        )
        if type(count.input_tokens) is not int or count.input_tokens < 0:
            raise ComparisonError("API đếm token trả về dữ liệu không hợp lệ")
        if count.input_tokens + settings.max_output_tokens > budget:
            raise ComparisonError(
                f"Input ({count.input_tokens} tokens) + dự phòng output ({settings.max_output_tokens}) "
                f"vượt context ({budget}); không cắt bớt CLO set, JD hoặc history", code="context_limit"
            )
        generation_options = {"temperature": settings.temperature} if settings.temperature is not None else {}
        response = client.responses.parse(
            timeout=settings.timeout,
            model=settings.model,
            instructions=instructions,
            input=input_messages,
            text_format=response_model,
            max_output_tokens=settings.max_output_tokens,
            truncation="disabled",
            store=False,
            **generation_options,
            **settings.reasoning_options,
            **search_options,
            **({"max_tool_calls": 5, "include": ["web_search_call.action.sources"]} if web_search else {}),
        )
        for item in response.output:
            if item.type == "message":
                for content in item.content:
                    if content.type == "refusal":
                        raise ComparisonError(f"Model từ chối tạo {operation_label} (refusal)", code="model_refusal")
        if response.status == "incomplete":
            details = getattr(response, "incomplete_details", None)
            reason = getattr(details, "reason", "unknown")
            code = "model_output_limit" if reason == "max_output_tokens" else "model_response_incomplete"
            raise ComparisonError(f"Model trả response chưa hoàn tất (incomplete: {reason}); không lưu {operation_label}", code=code)
        if response.status != "completed":
            raise ComparisonError(f"API không trả response completed; không lưu {operation_label}", code="invalid_response_status")
        if response.output_parsed is None:
            raise ComparisonError("Response không có structured output có thể phân tích", code="missing_structured_output")
        return response if web_search else response.output_parsed
    except openai.AuthenticationError as exc:
        raise ComparisonError("OpenAI từ chối xác thực; kiểm tra OPENAI_API_KEY", code="authentication_failed") from exc
    except openai.RateLimitError as exc:
        message = "OpenAI hết quota hoặc chưa có billing" if exc.code == "insufficient_quota" else "OpenAI vượt rate limit"
        raise ComparisonError(message, code="quota_exhausted" if exc.code == "insufficient_quota" else "rate_limited") from exc
    except openai.APITimeoutError as exc:
        raise ComparisonError("OpenAI timeout") from exc
    except openai.APIConnectionError as exc:
        raise ComparisonError("Không kết nối được OpenAI") from exc
    except openai.APIStatusError as exc:
        raise ComparisonError(f"OpenAI API lỗi HTTP {exc.status_code}; kiểm tra model/quyền truy cập/cấu hình", code="upstream_api_error") from exc
    except openai.APIError as exc:
        raise ComparisonError(f"OpenAI SDK trả lỗi API; không lưu {operation_label}", code="upstream_api_error") from exc
    except (ValidationError, json.JSONDecodeError) as exc:
        raise ComparisonError("Response không phân tích được thành JSON đúng schema; có thể chưa hoàn tất", code="invalid_structured_output") from exc
    finally:
        if owned_client:
            client.close()
