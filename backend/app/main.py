from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
PROJECT_DIR = BASE_DIR.parent
REPO_DIR = PROJECT_DIR.parent
LOG_DIR = PROJECT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

from prompt import IMAGE_TO_VIDEO_PROMPT_TEMPLATE, TEXT_SPLIT_PROMPT_TEMPLATE, VIDEO_PROMPT_PARAMETER_KEYS


logger = logging.getLogger("api_calls")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.FileHandler(LOG_DIR / "api_calls.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)


def env_url(name: str, default: str) -> str:
    value = (os.getenv(name) or "").strip()
    return (value or default).rstrip("/")


def env_text(name: str, default: str = "") -> str:
    value = (os.getenv(name) or "").strip()
    return value or default


OPENAI_BASE_URL = env_url("OPENAI_BASE_URL", "https://api.openai.com")
DMXAPI_BASE_URL = env_url("DMXAPI_BASE_URL", "https://www.dmxapi.cn")
DMXAPI_API_KEY = env_text("DMXAPI_API_KEY")


class ModelOption(BaseModel):
    id: str
    name: str
    provider: str
    description: str
    token_label: str = "API Token"
    prompt_label: str = "提示词"
    default_prompt: str = ""
    supports_real_api: bool = True
    token_from_env: bool = False
    min_images: int = 0
    max_images: int = 0
    parameters: list[dict[str, Any]] = Field(default_factory=list)


class FeatureTab(BaseModel):
    id: Literal["text_split", "text_to_image", "image_to_video"]
    name: str
    description: str
    models: list[ModelOption]


class TaskCreate(BaseModel):
    feature: str
    model_id: str
    token: str = ""
    prompt: str = ""
    source_text: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)


class TaskRecord(BaseModel):
    id: str
    feature: str
    model_id: str
    model_name: str
    status: Literal["queued", "running", "succeeded", "failed"]
    prompt: str
    source_text: str
    parameters: dict[str, Any]
    token_masked: str
    result: dict[str, Any]
    created_at: str
    finished_at: str | None = None
    error_message: str | None = None


VIDEO_PROMPT_FIELDS: list[dict[str, Any]] = [
    {"key": "story_plot", "label": "故事情节", "type": "textarea", "default": "", "placeholder": "填写整体故事情节。"},
    {"key": "character_info", "label": "角色信息", "type": "textarea", "default": "", "placeholder": "填写角色姓名、身份、外观、关系。"},
    {"key": "scene_info", "label": "场景信息", "type": "textarea", "default": "", "placeholder": "填写场景、时间、环境、光影氛围。"},
    {"key": "novel_text", "label": "小说原文", "type": "textarea", "default": "", "placeholder": "粘贴相关小说原文。"},
    {"key": "tweet_copy", "label": "推文文案", "type": "textarea", "default": "", "placeholder": "粘贴推文或口播文案。"},
    {"key": "previous_shots", "label": "章节文案前分镜信息", "type": "textarea", "default": "", "placeholder": "填写前 2 条左右分镜信息。"},
    {"key": "next_shots", "label": "章节文案后分镜信息", "type": "textarea", "default": "", "placeholder": "填写后 2 条左右分镜信息。"},
    {"key": "chapter_copy", "label": "章节文案", "type": "textarea", "default": "", "placeholder": "逐条填写章节文案列表。"},
]


TASKS: dict[str, TaskRecord] = {}


def build_model_tabs() -> list[FeatureTab]:
    return [
        FeatureTab(
            id="text_split",
            name="文字拆解",
            description="系统内置拆解提示词，直接输入文案并选择模型即可。",
            models=[
                ModelOption(
                    id="deepseek_v32_text",
                    name="DeepSeek V3.2",
                    provider="DeepSeek",
                    description="使用 DeepSeek 官方 chat 接口，模型名使用 deepseek-chat。",
                    token_label="DeepSeek API Key",
                    prompt_label="文字拆解提示词",
                    default_prompt=TEXT_SPLIT_PROMPT_TEMPLATE,
                ),
                ModelOption(
                    id="qwen35_plus_text",
                    name="Qwen3.5 Plus",
                    provider="DashScope",
                    description="使用 DashScope OpenAI 兼容接口，模型名使用 qwen3.5-plus。",
                    token_label="DashScope API Key",
                    prompt_label="文字拆解提示词",
                    default_prompt=TEXT_SPLIT_PROMPT_TEMPLATE,
                ),
                ModelOption(
                    id="gpt4o_text",
                    name="GPT-4o",
                    provider="OpenAI",
                    description="使用 OpenAI Chat Completions 接口，模型名使用 gpt-4o。",
                    token_label="OpenAI API Key",
                    prompt_label="文字拆解提示词",
                    default_prompt=TEXT_SPLIT_PROMPT_TEMPLATE,
                ),
            ],
        ),
        FeatureTab(
            id="text_to_image",
            name="文生图",
            description="",
            models=[
                ModelOption(
                    id="jimeng_image",
                    name="即梦文生图",
                    provider="DMXAPI / 即梦",
                    description="通过 DMXAPI 的 Seedream 4.0 文生图接口生成图片。",
                    token_label="DMXAPI_API_KEY（从 .env 读取）",
                    prompt_label="文生图提示词",
                    token_from_env=True,
                    parameters=[
                        {"key": "model", "label": "模型", "type": "select", "default": "doubao-seedream-4-0-250828", "options": ["doubao-seedream-4-0-250828"]},
                        {"key": "size", "label": "尺寸", "type": "text", "default": "2K"},
                        {"key": "count", "label": "期望出图数量", "type": "number", "default": 1, "min": 1, "max": 10},
                        {"key": "response_format", "label": "返回格式", "type": "select", "default": "url", "options": ["url", "b64_json"]},
                        {"key": "sequential_image_generation", "label": "连续出图", "type": "select", "default": "auto", "options": ["auto", "disabled"]},
                        {"key": "sequential_image_generation_max_images", "label": "连续出图上限", "type": "number", "default": 4, "min": 1, "max": 10},
                        {"key": "stream", "label": "流式返回", "type": "boolean", "default": False},
                        {"key": "watermark", "label": "添加水印", "type": "boolean", "default": False},
                    ],
                ),
                ModelOption(
                    id="openai_image",
                    name="OpenAI 文生图",
                    provider="DMXAPI / OpenAI",
                    description="通过 DMXAPI 的 GPT Image 接口生成图片。",
                    token_label="DMXAPI_API_KEY（从 .env 读取）",
                    prompt_label="文生图提示词",
                    token_from_env=True,
                    parameters=[
                        {"key": "model", "label": "模型", "type": "select", "default": "gpt-image-1", "options": ["gpt-image-1"]},
                        {"key": "size", "label": "尺寸", "type": "select", "default": "1024x1024", "options": ["1024x1024", "1024x1536", "1536x1024", "auto"]},
                        {"key": "background", "label": "背景", "type": "select", "default": "auto", "options": ["auto", "transparent", "opaque"]},
                        {"key": "moderation", "label": "审核强度", "type": "select", "default": "auto", "options": ["auto", "low"]},
                        {"key": "output_format", "label": "输出格式", "type": "select", "default": "png", "options": ["png", "jpeg", "webp"]},
                        {"key": "quality", "label": "质量", "type": "select", "default": "high", "options": ["auto", "high", "medium", "low"]},
                        {"key": "output_compression", "label": "压缩质量", "type": "number", "default": 100, "min": 0, "max": 100},
                        {"key": "count", "label": "生成数量", "type": "number", "default": 1, "min": 1, "max": 3},
                    ],
                ),
                ModelOption(
                    id="qwen_image_max",
                    name="qwen-image-max（通义千问）",
                    provider="DashScope",
                    description="使用 DashScope 文生图接口。",
                    token_label="DashScope API Key",
                    prompt_label="文生图提示词",
                    parameters=[
                        {"key": "model", "label": "模型", "type": "select", "default": "qwen-image-max", "options": ["qwen-image-max", "qwen-image-2.0-pro", "qwen-image-2.0", "qwen-image-plus", "qwen-image"]},
                        {"key": "resolution", "label": "分辨率", "type": "select", "default": "720p", "options": ["480p", "720p", "1080p"]},
                        {"key": "aspect_ratio", "label": "宽高比", "type": "select", "default": "16:9", "options": ["16:9", "9:16", "1:1", "4:3", "3:4"]},
                        {"key": "response_format", "label": "响应格式", "type": "select", "default": "url", "options": ["url", "b64_json"]},
                        {"key": "timeout", "label": "超时", "type": "number", "default": 120, "min": 10, "max": 300},
                        {"key": "retries", "label": "重试次数", "type": "number", "default": 0, "min": 0, "max": 3},
                        {"key": "count", "label": "生成数量", "type": "number", "default": 1, "min": 1, "max": 3},
                    ],
                ),
            ],
        ),
        FeatureTab(
            id="image_to_video",
            name="图生视频",
            description="支持多图上传。即梦视频会先提交任务，再按远端任务 ID 限次轮询结果。",
            models=[
                ModelOption(
                    id="jimeng_i2v",
                    name="即梦首帧生成视频",
                    provider="DMXAPI / 即梦",
                    description="通过 DMXAPI 即梦首帧图生视频接口提交并轮询结果。",
                    token_label="DMXAPI_API_KEY（从 .env 读取）",
                    prompt_label="视频提示词",
                    token_from_env=True,
                    min_images=1,
                    max_images=1,
                    parameters=[
                        *VIDEO_PROMPT_FIELDS,
                        {"key": "model", "label": "模型", "type": "select", "default": "doubao-seedance-2-0-260128", "options": ["doubao-seedance-2-0-260128"]},
                        {"key": "resolution", "label": "分辨率", "type": "select", "default": "720p", "options": ["480p", "720p"]},
                        {"key": "ratio", "label": "画幅比例", "type": "select", "default": "adaptive", "options": ["adaptive", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"]},
                        {"key": "duration", "label": "时长", "type": "select", "default": "5", "options": ["4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15"]},
                        {"key": "watermark", "label": "添加水印", "type": "boolean", "default": False},
                        {"key": "camera_fixed", "label": "固定运镜", "type": "boolean", "default": False},
                        {"key": "seed", "label": "随机种子", "type": "number", "default": -1},
                        {"key": "generate_audio", "label": "生成音频", "type": "boolean", "default": False},
                        {"key": "return_last_frame", "label": "返回尾帧", "type": "boolean", "default": False},
                        {"key": "enable_web_search", "label": "联网搜索", "type": "boolean", "default": False},
                        {"key": "poll_interval", "label": "轮询间隔秒数", "type": "number", "default": 8, "min": 3, "max": 30},
                        {"key": "max_attempts", "label": "轮询上限次数", "type": "number", "default": 12, "min": 1, "max": 60},
                        {"key": "timeout", "label": "提交超时", "type": "number", "default": 180, "min": 30, "max": 900},
                    ],
                ),
                ModelOption(
                    id="jimeng_flf_i2v",
                    name="即梦首尾帧生成视频",
                    provider="DMXAPI / 即梦",
                    description="通过 DMXAPI 即梦首尾帧图生视频接口提交并轮询结果。",
                    token_label="DMXAPI_API_KEY（从 .env 读取）",
                    prompt_label="视频提示词",
                    token_from_env=True,
                    min_images=2,
                    max_images=2,
                    parameters=[
                        *VIDEO_PROMPT_FIELDS,
                        {"key": "model", "label": "模型", "type": "select", "default": "doubao-seedance-2-0-260128", "options": ["doubao-seedance-2-0-260128"]},
                        {"key": "resolution", "label": "分辨率", "type": "select", "default": "720p", "options": ["480p", "720p"]},
                        {"key": "ratio", "label": "画幅比例", "type": "select", "default": "adaptive", "options": ["adaptive", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"]},
                        {"key": "duration", "label": "时长", "type": "select", "default": "5", "options": ["-1", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15"]},
                        {"key": "watermark", "label": "添加水印", "type": "boolean", "default": False},
                        {"key": "camera_fixed", "label": "固定运镜", "type": "boolean", "default": False},
                        {"key": "seed", "label": "随机种子", "type": "number", "default": -1},
                        {"key": "generate_audio", "label": "生成音频", "type": "boolean", "default": False},
                        {"key": "return_last_frame", "label": "返回尾帧", "type": "boolean", "default": False},
                        {"key": "poll_interval", "label": "轮询间隔秒数", "type": "number", "default": 8, "min": 3, "max": 30},
                        {"key": "max_attempts", "label": "轮询上限次数", "type": "number", "default": 12, "min": 1, "max": 60},
                        {"key": "timeout", "label": "提交超时", "type": "number", "default": 180, "min": 30, "max": 900},
                    ],
                ),
                ModelOption(
                    id="kling_i2v",
                    name="可灵图生视频",
                    provider="DMXAPI / 可灵",
                    description="通过 DMXAPI 可灵图生视频接口提交任务。",
                    token_label="DMXAPI_API_KEY（从 .env 读取）",
                    prompt_label="视频提示词",
                    token_from_env=True,
                    min_images=1,
                    max_images=1,
                    parameters=[
                        *VIDEO_PROMPT_FIELDS,
                        {"key": "model", "label": "模型", "type": "select", "default": "kling-v2.6", "options": ["kling-v2.6"]},
                        {"key": "duration", "label": "时长", "type": "select", "default": "5", "options": ["5", "10"]},
                        {"key": "mode", "label": "生成模式", "type": "select", "default": "std", "options": ["std", "pro"]},
                        {"key": "cfg_scale", "label": "CFG Scale", "type": "number", "default": 0.5, "min": 0, "max": 1},
                        {"key": "watermark", "label": "添加水印", "type": "boolean", "default": False},
                        {"key": "timeout", "label": "提交超时", "type": "number", "default": 180, "min": 30, "max": 900},
                    ],
                ),
                ModelOption(
                    id="wan_i2v",
                    name="wan2.6-i2v（图生视频）",
                    provider="DashScope",
                    description="Wan 首帧图生视频，当前最多支持 1 张图。",
                    token_label="DashScope API Key",
                    prompt_label="视频提示词",
                    min_images=1,
                    max_images=1,
                    parameters=[
                        *VIDEO_PROMPT_FIELDS,
                        {"key": "model", "label": "模型", "type": "select", "default": "wan2.6-i2v", "options": ["wan2.6-i2v", "wan2.6-i2v-flash"]},
                        {"key": "resolution", "label": "分辨率", "type": "select", "default": "720P", "options": ["720P", "1080P"]},
                        {"key": "duration", "label": "时长", "type": "number", "default": 5, "min": 2, "max": 15},
                        {"key": "prompt_extend", "label": "提示词扩写", "type": "boolean", "default": True},
                        {"key": "watermark", "label": "添加水印", "type": "boolean", "default": False},
                        {"key": "timeout", "label": "提交超时", "type": "number", "default": 900, "min": 30, "max": 1800},
                    ],
                ),
                ModelOption(
                    id="wan_kf2v",
                    name="wan2.2-kf2v-flash（首尾帧生视频）",
                    provider="DashScope",
                    description="Wan 首尾帧图生视频，需上传 2 张图。",
                    token_label="DashScope API Key",
                    prompt_label="视频提示词",
                    min_images=2,
                    max_images=2,
                    parameters=[
                        *VIDEO_PROMPT_FIELDS,
                        {"key": "model", "label": "模型", "type": "select", "default": "wan2.2-kf2v-flash", "options": ["wan2.2-kf2v-flash"]},
                        {"key": "resolution", "label": "分辨率", "type": "select", "default": "720P", "options": ["480P", "720P", "1080P"]},
                        {"key": "prompt_extend", "label": "提示词扩写", "type": "boolean", "default": True},
                        {"key": "watermark", "label": "添加水印", "type": "boolean", "default": False},
                        {"key": "timeout", "label": "提交超时", "type": "number", "default": 900, "min": 30, "max": 1800},
                    ],
                ),
                ModelOption(
                    id="vidu_multiframe",
                    name="Vidu Multi-Frame（多关键帧）",
                    provider="Vidu",
                    description="Vidu 多关键帧视频，第一张作为起始帧，后续图片作为关键帧。",
                    token_label="Vidu API Key",
                    prompt_label="视频提示词",
                    min_images=3,
                    max_images=10,
                    parameters=[
                        *VIDEO_PROMPT_FIELDS,
                        {"key": "model", "label": "模型", "type": "select", "default": "viduq2-turbo", "options": ["viduq2-turbo"]},
                        {"key": "resolution", "label": "分辨率", "type": "select", "default": "720p", "options": ["540p", "720p", "1080p"]},
                        {"key": "duration", "label": "每段时长", "type": "number", "default": 5, "min": 2, "max": 7},
                        {"key": "timeout", "label": "提交超时", "type": "number", "default": 900, "min": 30, "max": 1800},
                    ],
                ),
            ],
        ),
    ]


MODEL_TABS = build_model_tabs()


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def mask_token(token: str) -> str:
    value = (token or "").strip()
    if not value:
        return "未填写"
    if value == DMXAPI_API_KEY:
        return "env:DMXAPI_API_KEY"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def log_api(event: str, **payload: Any) -> None:
    logger.info("%s %s", event, json.dumps(payload, ensure_ascii=False))


def int_parameter(value: Any, *, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        result = int(float(value))
    except (TypeError, ValueError):
        result = default
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


def float_parameter(value: Any, *, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = default
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


def string_parameter(value: Any, default: str = "") -> str:
    text = str(value or default).strip()
    return text or default


def bool_parameter(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enable", "enabled"}


def make_http_client(timeout: int | float) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, trust_env=True)


def image_data_url(item: dict[str, str]) -> str:
    content_type = item.get("content_type") or "image/jpeg"
    return f"data:{content_type};base64,{item['b64']}"


def find_model(model_id: str) -> ModelOption | None:
    for tab in MODEL_TABS:
        for model in tab.models:
            if model.id == model_id:
                return model
    return None


def save_task(
    payload: TaskCreate,
    model: ModelOption,
    status: Literal["queued", "running", "succeeded", "failed"],
    result: dict[str, Any],
    error: str | None = None,
) -> TaskRecord:
    task = TaskRecord(
        id=str(uuid4()),
        feature=payload.feature,
        model_id=model.id,
        model_name=model.name,
        status=status,
        prompt=payload.prompt,
        source_text=payload.source_text,
        parameters=payload.parameters,
        token_masked=mask_token(payload.token),
        result=result,
        created_at=now_iso(),
        finished_at=now_iso() if status in {"succeeded", "failed"} else None,
        error_message=error,
    )
    TASKS[task.id] = task
    return task


def update_task(
    task_id: str,
    status: Literal["queued", "running", "succeeded", "failed"],
    result: dict[str, Any],
    error: str | None = None,
) -> TaskRecord | None:
    task = TASKS.get(task_id)
    if not task:
        return None
    task.status = status
    task.result = result
    task.error_message = error
    task.finished_at = now_iso() if status in {"succeeded", "failed"} else None
    TASKS[task_id] = task
    return task


def format_exception(exc: Exception) -> str:
    return f"{exc.__class__.__name__}: {exc}"


VIDEO_FIELD_LABELS = {
    "story_plot": "故事情节",
    "character_info": "角色信息",
    "scene_info": "场景信息",
    "novel_text": "小说原文",
    "tweet_copy": "推文文案",
    "previous_shots": "章节文案前分镜信息",
    "next_shots": "章节文案后分镜信息",
    "chapter_copy": "章节文案",
}


def render_text_split_prompt(source_text: str) -> str:
    return f"{TEXT_SPLIT_PROMPT_TEMPLATE}\n\n## 待拆解文案\n{source_text.strip()}"


def build_video_prompt(parameters: dict[str, Any]) -> str:
    parts: list[str] = [IMAGE_TO_VIDEO_PROMPT_TEMPLATE.strip()]
    has_content = False
    for key in VIDEO_PROMPT_PARAMETER_KEYS:
        value = string_parameter(parameters.get(key))
        if value:
            has_content = True
            parts.append(f"\n\n## {VIDEO_FIELD_LABELS.get(key, key)}\n{value}")
    if not has_content:
        return ""
    return "".join(parts).strip()


def build_text_to_image_prompt(source_text: str, prompt: str) -> str:
    source_text = source_text.strip()
    prompt = prompt.strip()
    if source_text and prompt:
        return f"{source_text}\n\n{prompt}"
    return prompt or source_text


async def post_json(url: str, *, headers: dict[str, str], body: dict[str, Any], timeout: int) -> dict[str, Any]:
    async with make_http_client(timeout) as client:
        response = await client.post(url, headers=headers, json=body)
    if response.status_code >= 400:
        raise RuntimeError(f"{response.status_code} {response.text[:1200]}")
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("接口未返回 JSON 对象")
    return data


async def post_dmxapi_json(path: str, *, api_key: str, body: dict[str, Any], timeout: int) -> dict[str, Any]:
    if not api_key:
        raise ValueError("请先配置 DMXAPI_API_KEY")
    try:
        return await post_json(
            f"{DMXAPI_BASE_URL}{path}",
            headers={"Authorization": f"Bearer {api_key}"},
            body=body,
            timeout=timeout,
        )
    except Exception as exc:
        if isinstance(exc, RuntimeError):
            raise RuntimeError(f"DMXAPI 调用失败：{exc}") from exc
        raise


def extract_text_content(value: Any) -> str:
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            return value["text"]
        for nested in value.values():
            result = extract_text_content(nested)
            if result:
                return result
    elif isinstance(value, list):
        for item in value:
            result = extract_text_content(item)
            if result:
                return result
    elif isinstance(value, str):
        return value
    return ""


def extract_chat_content(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, list):
            return "\n".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and isinstance(item.get("text"), str)
            ).strip()
        if isinstance(content, str):
            return content.strip()
    return extract_text_content(data).strip()


def extract_dmx_response_text(data: Any) -> str:
    if isinstance(data, dict):
        output = data.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and isinstance(part.get("text"), str):
                            return part["text"]
        for nested in data.values():
            result = extract_dmx_response_text(nested)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = extract_dmx_response_text(item)
            if result:
                return result
    return ""


def parse_json_text(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        return {}
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return {"raw_text": stripped}
    return data if isinstance(data, dict) else {"raw_payload": data}


def extract_task_id(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("task_id", "taskId", "id"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()
        for nested in value.values():
            result = extract_task_id(nested)
            if result:
                return result
    elif isinstance(value, list):
        for item in value:
            result = extract_task_id(item)
            if result:
                return result
    return None


def extract_dmx_video_url(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, item in value.items():
            lower_key = key.lower()
            if lower_key in {"video_url", "url"} and isinstance(item, str) and ".mp4" in item:
                return item.strip()
            nested = extract_dmx_video_url(item)
            if nested:
                return nested
    elif isinstance(value, list):
        for item in value:
            nested = extract_dmx_video_url(item)
            if nested:
                return nested
    elif isinstance(value, str):
        match = re.search(r"https?://\S+?\.mp4(?:\?\S*)?", value)
        if match:
            return match.group(0)
    return None


def extract_image_assets(value: Any) -> list[dict[str, str]]:
    assets: list[dict[str, str]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("url"), str) and re.search(r"\.(png|jpg|jpeg|webp)(?:\?|$)", node["url"], re.I):
                assets.append({"type": "image", "url": node["url"]})
            if isinstance(node.get("b64_json"), str):
                assets.append({"type": "image", "b64_json": node["b64_json"]})
            for nested in node.values():
                walk(nested)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, str):
            if re.search(r"https?://\S+?\.(png|jpg|jpeg|webp)(?:\?\S*)?$", node, re.I):
                assets.append({"type": "image", "url": node})

    walk(value)
    unique: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in assets:
        key = (item.get("type", ""), item.get("url", item.get("b64_json", "")))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def normalize_status(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def parse_seedance_query_payload(data: dict[str, Any]) -> dict[str, Any]:
    return parse_json_text(extract_dmx_response_text(data))


def extract_seedance_status(data: dict[str, Any], parsed: dict[str, Any]) -> str:
    for source in (parsed, data):
        if isinstance(source, dict):
            for key in ("status", "task_status", "state"):
                value = source.get(key)
                if isinstance(value, str) and value.strip():
                    return normalize_status(value)
    return ""


async def query_seedance_video_result_once(api_key: str, remote_task_id: str, model_name: str, timeout: int = 60) -> dict[str, Any]:
    body = {
        "model": "seedance-2-0-get",
        "input": remote_task_id,
    }
    query_data = await post_dmxapi_json("/v1/responses", api_key=api_key, body=body, timeout=min(timeout, 180))
    query_payload = parse_seedance_query_payload(query_data)
    status = extract_seedance_status(query_data, query_payload)
    video_url = extract_dmx_video_url(query_payload) or extract_dmx_video_url(query_data)
    log_api(
        "request.image_to_video_result",
        model=model_name,
        remote_task_id=remote_task_id,
        status=status or "unknown",
        has_video=bool(video_url),
    )
    return {
        "task_id": remote_task_id,
        "status": status or "unknown",
        "video_url": video_url,
        "provider_response": query_data,
        "query_payload": query_payload,
    }


async def poll_seedance_video_result(
    api_key: str,
    remote_task_id: str,
    model_name: str,
    *,
    max_attempts: int,
    poll_interval: int,
    timeout: int,
) -> dict[str, Any]:
    last_result: dict[str, Any] = {"task_id": remote_task_id, "status": "running"}
    for attempt in range(1, max_attempts + 1):
        result = await query_seedance_video_result_once(api_key, remote_task_id, model_name, timeout=timeout)
        result["attempt"] = attempt
        last_result = result
        status = normalize_status(str(result.get("status") or ""))
        if result.get("video_url"):
            return result
        if status in {"failed", "error", "cancelled", "canceled", "expired"}:
            raise RuntimeError(f"{model_name} 远端任务失败：{json.dumps(result.get('query_payload') or result.get('provider_response'), ensure_ascii=False)[:1200]}")
        if attempt < max_attempts:
            await asyncio.sleep(poll_interval)
    return last_result


async def call_chat_model(payload: TaskCreate, model: ModelOption) -> dict[str, Any]:
    if not payload.source_text.strip():
        raise ValueError("请填写待拆解文案")
    if not payload.token.strip():
        raise ValueError("请先填写模型 Token")

    prompt = render_text_split_prompt(payload.source_text)
    if payload.model_id == "deepseek_v32_text":
        url = "https://api.deepseek.com/chat/completions"
        api_model = "deepseek-chat"
    elif payload.model_id == "qwen35_plus_text":
        url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        api_model = "qwen3.5-plus"
    elif payload.model_id == "gpt4o_text":
        url = f"{OPENAI_BASE_URL}/v1/chat/completions"
        api_model = "gpt-4o"
    else:
        raise ValueError("不支持的文字拆解模型")

    body = {
        "model": api_model,
        "messages": [
            {"role": "system", "content": "你是一个分镜拆解助手，请严格遵守提示词要求输出。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    log_api(
        "request.text_split",
        model=model.id,
        url=url,
        api_model=api_model,
        source_length=len(payload.source_text),
        rendered_prompt_length=len(prompt),
    )
    try:
        data = await post_json(url, headers={"Authorization": f"Bearer {payload.token}"}, body=body, timeout=120)
    except httpx.TimeoutException as exc:
        raise RuntimeError(f"{model.name} 调用超时：120 秒内未收到响应，请检查网络连通性、代理设置，或稍后重试。") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"{model.name} 网络请求失败：{exc}") from exc
    return {"message": "文字拆解调用完成", "raw": extract_chat_content(data), "provider_response": data}


async def call_image_model(payload: TaskCreate, model: ModelOption) -> dict[str, Any]:
    final_prompt = build_text_to_image_prompt(payload.source_text, payload.prompt)
    if not final_prompt:
        raise ValueError("请填写文生图提示词")

    if payload.model_id == "jimeng_image":
        requested_count = int_parameter(payload.parameters.get("count"), default=1, minimum=1, maximum=10)
        sequential_mode = string_parameter(payload.parameters.get("sequential_image_generation"), "auto")
        body = {
            "model": string_parameter(payload.parameters.get("model"), "doubao-seedream-4-0-250828"),
            "prompt": final_prompt,
            "size": string_parameter(payload.parameters.get("size"), "2K"),
            "response_format": string_parameter(payload.parameters.get("response_format"), "url"),
            "sequential_image_generation": sequential_mode,
            "stream": bool_parameter(payload.parameters.get("stream"), default=False),
            "watermark": bool_parameter(payload.parameters.get("watermark"), default=False),
        }
        if sequential_mode != "disabled":
            body["sequential_image_generation_options"] = {
                "max_images": int_parameter(
                    payload.parameters.get("sequential_image_generation_max_images"),
                    default=requested_count,
                    minimum=1,
                    maximum=10,
                )
            }
        log_api("request.text_to_image", model=model.id, provider="dmxapi_jimeng")
        data = await post_dmxapi_json("/v1/images/generations", api_key=DMXAPI_API_KEY, body=body, timeout=180)
        assets = extract_image_assets(data)
        message = "即梦文生图调用完成"
        if requested_count > 1 and len(assets) < requested_count:
            message = f"即梦文生图调用完成：请求 {requested_count} 张，接口实际返回 {len(assets)} 张"
        return {"message": message, "assets": assets, "provider_response": data}

    if payload.model_id == "openai_image":
        body = {
            "model": string_parameter(payload.parameters.get("model"), "gpt-image-1"),
            "prompt": final_prompt,
            "size": string_parameter(payload.parameters.get("size"), "1024x1024"),
            "background": string_parameter(payload.parameters.get("background"), "auto"),
            "moderation": string_parameter(payload.parameters.get("moderation"), "auto"),
            "output_format": string_parameter(payload.parameters.get("output_format"), "png"),
            "quality": string_parameter(payload.parameters.get("quality"), "high"),
            "output_compression": int_parameter(payload.parameters.get("output_compression"), default=100, minimum=0, maximum=100),
            "n": int_parameter(payload.parameters.get("count"), default=1, minimum=1, maximum=3),
        }
        log_api("request.text_to_image", model=model.id, provider="dmxapi_openai")
        data = await post_dmxapi_json("/v1/images/generations", api_key=DMXAPI_API_KEY, body=body, timeout=180)
        return {"message": "OpenAI 文生图调用完成", "assets": extract_image_assets(data), "provider_response": data}

    if payload.model_id == "qwen_image_max":
        token = payload.token.strip()
        if not token:
            raise ValueError("请先填写模型 Token")
        selected_model = string_parameter(payload.parameters.get("model"), "qwen-image-max")
        count = int_parameter(payload.parameters.get("count"), default=1, minimum=1, maximum=3)
        effective_count = 1 if selected_model in {"qwen-image-max", "qwen-image-plus", "qwen-image"} else count
        size_map = {
            ("480p", "16:9"): "832*480",
            ("480p", "9:16"): "480*832",
            ("480p", "1:1"): "768*768",
            ("720p", "16:9"): "1280*720",
            ("720p", "9:16"): "720*1280",
            ("720p", "1:1"): "1024*1024",
            ("720p", "4:3"): "1152*864",
            ("720p", "3:4"): "864*1152",
            ("1080p", "16:9"): "1920*1080",
            ("1080p", "9:16"): "1080*1920",
            ("1080p", "1:1"): "1328*1328",
        }
        size = size_map.get(
            (
                string_parameter(payload.parameters.get("resolution"), "720p"),
                string_parameter(payload.parameters.get("aspect_ratio"), "16:9"),
            ),
            "1280*720",
        )
        body = {
            "model": selected_model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": final_prompt}],
                    }
                ]
            },
            "parameters": {
                "size": size,
                "n": effective_count,
                "watermark": False,
            },
        }
        timeout = int_parameter(payload.parameters.get("timeout"), default=120, minimum=10, maximum=300)
        log_api("request.text_to_image", model=model.id, provider="dashscope")
        data = await post_json(
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
            headers={"Authorization": f"Bearer {token}"},
            body=body,
            timeout=timeout,
        )
        return {"message": "Qwen 文生图调用完成", "assets": extract_image_assets(data), "provider_response": data}

    raise ValueError("不支持的文生图模型")


async def read_upload_images(files: list[UploadFile], max_images: int) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for upload in files[:max_images]:
        content = await upload.read()
        if not content:
            continue
        items.append(
            {
                "filename": upload.filename or "image.jpg",
                "content_type": upload.content_type or "image/jpeg",
                "b64": base64.b64encode(content).decode("utf-8"),
            }
        )
    return items


async def call_video_model(
    model_id: str,
    token: str,
    parameters: dict[str, Any],
    files: list[UploadFile],
    model: ModelOption,
) -> dict[str, Any]:
    if len(files) < model.min_images:
        raise ValueError(f"{model.name} 至少需要上传 {model.min_images} 张图片")
    if model.max_images and len(files) > model.max_images:
        raise ValueError(f"{model.name} 当前最多支持上传 {model.max_images} 张图片，你上传了 {len(files)} 张")

    prompt = build_video_prompt(parameters)
    if not prompt:
        raise ValueError("请填写章节文案、角色信息、场景信息等图生视频参数")

    effective_token = DMXAPI_API_KEY if model.token_from_env else token.strip()
    if not effective_token:
        raise ValueError("请先填写模型 Token")

    encoded_images = await read_upload_images(files, model.max_images or len(files))
    log_api("request.image_to_video", model=model_id, image_count=len(encoded_images))

    if model_id == "jimeng_i2v":
        body = {
            "model": string_parameter(parameters.get("model"), "doubao-seedance-2-0-260128"),
            "input": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_data_url(encoded_images[0])}, "role": "first_frame"},
            ],
            "resolution": string_parameter(parameters.get("resolution"), "720p"),
            "ratio": string_parameter(parameters.get("ratio"), "adaptive"),
            "duration": int_parameter(parameters.get("duration"), default=5, minimum=4, maximum=15),
            "watermark": bool_parameter(parameters.get("watermark"), default=False),
            "camera_fixed": bool_parameter(parameters.get("camera_fixed"), default=False),
            "seed": int_parameter(parameters.get("seed"), default=-1),
            "generate_audio": bool_parameter(parameters.get("generate_audio"), default=False),
            "return_last_frame": bool_parameter(parameters.get("return_last_frame"), default=False),
        }
        if bool_parameter(parameters.get("enable_web_search"), default=False):
            body["tools"] = [{"type": "web_search"}]
        data = await post_dmxapi_json(
            "/v1/responses",
            api_key=effective_token,
            body=body,
            timeout=int_parameter(parameters.get("timeout"), default=180, minimum=30, maximum=900),
        )
        remote_task_id = extract_task_id(data)
        if not remote_task_id:
            raise RuntimeError(f"{model.name} 提交成功，但未拿到远端任务 ID：{json.dumps(data, ensure_ascii=False)[:1200]}")
        return {
            "message": "即梦首帧生成视频任务已提交，请使用任务 ID 查询生成结果。",
            "task_id": remote_task_id,
            "task_status": "running",
            "provider_response": data,
        }

    if model_id == "jimeng_flf_i2v":
        body = {
            "model": string_parameter(parameters.get("model"), "doubao-seedance-2-0-260128"),
            "input": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_data_url(encoded_images[0])}, "role": "first_frame"},
                {"type": "image_url", "image_url": {"url": image_data_url(encoded_images[1])}, "role": "last_frame"},
            ],
            "resolution": string_parameter(parameters.get("resolution"), "720p"),
            "ratio": string_parameter(parameters.get("ratio"), "adaptive"),
            "duration": int_parameter(parameters.get("duration"), default=5, minimum=-1, maximum=15),
            "watermark": bool_parameter(parameters.get("watermark"), default=False),
            "camera_fixed": bool_parameter(parameters.get("camera_fixed"), default=False),
            "seed": int_parameter(parameters.get("seed"), default=-1),
            "generate_audio": bool_parameter(parameters.get("generate_audio"), default=False),
            "return_last_frame": bool_parameter(parameters.get("return_last_frame"), default=False),
        }
        data = await post_dmxapi_json(
            "/v1/responses",
            api_key=effective_token,
            body=body,
            timeout=int_parameter(parameters.get("timeout"), default=180, minimum=30, maximum=900),
        )
        remote_task_id = extract_task_id(data)
        if not remote_task_id:
            raise RuntimeError(f"{model.name} 提交成功，但未拿到远端任务 ID：{json.dumps(data, ensure_ascii=False)[:1200]}")
        return {
            "message": "即梦首尾帧生成视频任务已提交，请使用任务 ID 查询生成结果。",
            "task_id": remote_task_id,
            "task_status": "running",
            "provider_response": data,
        }

    if model_id == "kling_i2v":
        body = {
            "model": string_parameter(parameters.get("model"), "kling-v2.6"),
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": image_data_url(encoded_images[0])},
                    ],
                }
            ],
            "duration": string_parameter(parameters.get("duration"), "5"),
            "mode": string_parameter(parameters.get("mode"), "std"),
            "cfg_scale": float_parameter(parameters.get("cfg_scale"), default=0.5, minimum=0.0, maximum=1.0),
            "watermark": bool_parameter(parameters.get("watermark"), default=False),
        }
        data = await post_dmxapi_json(
            "/v1/responses",
            api_key=effective_token,
            body=body,
            timeout=int_parameter(parameters.get("timeout"), default=180, minimum=30, maximum=900),
        )
        remote_task_id = extract_task_id(data)
        video_url = extract_dmx_video_url(data)
        return {
            "message": "可灵图生视频任务已提交" if not video_url else "可灵图生视频调用完成",
            "task_id": remote_task_id,
            "video_url": video_url,
            "task_status": "succeeded" if video_url else "running",
            "provider_response": data,
        }

    if model_id == "wan_i2v":
        body = {
            "model": string_parameter(parameters.get("model"), "wan2.6-i2v"),
            "input": {
                "prompt": prompt,
                "img_url": image_data_url(encoded_images[0]),
            },
            "parameters": {
                "resolution": string_parameter(parameters.get("resolution"), "720P"),
                "duration": int_parameter(parameters.get("duration"), default=5, minimum=2, maximum=15),
                "prompt_extend": bool_parameter(parameters.get("prompt_extend"), default=True),
                "watermark": bool_parameter(parameters.get("watermark"), default=False),
            },
        }
        data = await post_json(
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis",
            headers={"Authorization": f"Bearer {effective_token}", "X-DashScope-Async": "enable"},
            body=body,
            timeout=int_parameter(parameters.get("timeout"), default=900, minimum=30, maximum=1800),
        )
        return {
            "message": "Wan 图生视频任务已提交",
            "task_status": "running",
            "task_id": extract_task_id(data),
            "provider_response": data,
        }

    if model_id == "wan_kf2v":
        body = {
            "model": string_parameter(parameters.get("model"), "wan2.2-kf2v-flash"),
            "input": {
                "prompt": prompt,
                "first_frame_url": image_data_url(encoded_images[0]),
                "last_frame_url": image_data_url(encoded_images[1]),
            },
            "parameters": {
                "resolution": string_parameter(parameters.get("resolution"), "720P"),
                "prompt_extend": bool_parameter(parameters.get("prompt_extend"), default=True),
                "watermark": bool_parameter(parameters.get("watermark"), default=False),
            },
        }
        data = await post_json(
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/image2video/video-synthesis",
            headers={"Authorization": f"Bearer {effective_token}", "X-DashScope-Async": "enable"},
            body=body,
            timeout=int_parameter(parameters.get("timeout"), default=900, minimum=30, maximum=1800),
        )
        return {
            "message": "Wan 首尾帧生视频任务已提交",
            "task_status": "running",
            "task_id": extract_task_id(data),
            "provider_response": data,
        }

    if model_id == "vidu_multiframe":
        body = {
            "model": string_parameter(parameters.get("model"), "viduq2-turbo"),
            "start_image": image_data_url(encoded_images[0]),
            "image_settings": [
                {
                    "key_image": image_data_url(item),
                    "prompt": prompt,
                    "duration": int_parameter(parameters.get("duration"), default=5, minimum=2, maximum=7),
                }
                for item in encoded_images[1:]
            ],
            "resolution": string_parameter(parameters.get("resolution"), "720p").lower(),
        }
        data = await post_json(
            "https://api.vidu.com/ent/v2/multiframe",
            headers={"Authorization": f"Token {effective_token}"},
            body=body,
            timeout=int_parameter(parameters.get("timeout"), default=900, minimum=30, maximum=1800),
        )
        return {
            "message": "Vidu 多关键帧视频任务已提交",
            "task_status": "running",
            "task_id": extract_task_id(data),
            "provider_response": data,
        }

    raise ValueError("不支持的图生视频模型")


app = FastAPI(title="AI 创作控制台 API", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/model-tabs", response_model=list[FeatureTab])
def get_model_tabs() -> list[FeatureTab]:
    return MODEL_TABS


@app.post("/api/tasks", response_model=TaskRecord)
async def create_task(payload: TaskCreate) -> TaskRecord:
    model = find_model(payload.model_id)
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")
    try:
        if payload.feature == "text_split":
            result = await call_chat_model(payload, model)
        elif payload.feature == "text_to_image":
            result = await call_image_model(payload, model)
        else:
            raise ValueError("图生视频请使用 /api/video-tasks 上传图片")
        task = save_task(payload, model, "succeeded", result)
        log_api("success.task", task_id=task.id, feature=payload.feature, model=model.id)
        return task
    except Exception as exc:
        error = format_exception(exc)
        task = save_task(payload, model, "failed", {"message": "调用失败", "error": error}, error)
        log_api("error.task", task_id=task.id, feature=payload.feature, model=model.id, error=error)
        return task


@app.post("/api/video-tasks", response_model=TaskRecord)
async def create_video_task(
    model_id: str = Form(...),
    token: str = Form(""),
    prompt: str = Form(""),
    parameters: str = Form("{}"),
    files: list[UploadFile] = File(default=[]),
) -> TaskRecord:
    model = find_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")
    try:
        params = json.loads(parameters or "{}")
    except json.JSONDecodeError:
        params = {}
    payload = TaskCreate(
        feature="image_to_video",
        model_id=model_id,
        token=token,
        prompt=prompt,
        source_text=f"uploaded_images={len(files)}",
        parameters=params,
    )
    try:
        result = await call_video_model(model_id, token, params, files, model)
        status: Literal["queued", "running", "succeeded", "failed"] = "succeeded" if result.get("video_url") else "running"
        task = save_task(payload, model, status, result)
        log_api(
            "success.video_task",
            task_id=task.id,
            model=model.id,
            remote_task_id=result.get("task_id"),
            has_video=bool(result.get("video_url")),
            status=status,
        )
        return task
    except Exception as exc:
        error = format_exception(exc)
        task = save_task(payload, model, "failed", {"message": "调用失败", "error": error}, error)
        log_api("error.video_task", task_id=task.id, model=model.id, error=error)
        return task


@app.get("/api/tasks", response_model=list[TaskRecord])
def list_tasks() -> list[TaskRecord]:
    return sorted(TASKS.values(), key=lambda item: item.created_at, reverse=True)


@app.get("/api/tasks/{task_id}", response_model=TaskRecord)
def get_task(task_id: str) -> TaskRecord:
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@app.get("/api/video-tasks/{task_id}/result")
async def get_video_task_result(task_id: str) -> dict[str, Any]:
    local_task = TASKS.get(task_id)
    remote_task_id = task_id
    model_id = "jimeng_i2v"

    if local_task:
        if local_task.feature != "image_to_video":
            raise HTTPException(status_code=400, detail="该任务不是图生视频任务")
        model_id = local_task.model_id
        remote_task_id = string_parameter(local_task.result.get("task_id"), task_id)
        existing_video = string_parameter(local_task.result.get("video_url"))
        if existing_video:
            return {
                "local_task_id": local_task.id,
                "remote_task_id": remote_task_id,
                "status": local_task.status,
                "video_url": existing_video,
                "result": local_task.result,
            }

    if model_id not in {"jimeng_i2v", "jimeng_flf_i2v"} and not remote_task_id.startswith("cgt-"):
        raise HTTPException(status_code=400, detail="当前仅支持查询即梦远端视频任务")
    if not DMXAPI_API_KEY:
        raise HTTPException(status_code=400, detail="未配置 DMXAPI_API_KEY，无法查询视频结果")

    result = await query_seedance_video_result_once(DMXAPI_API_KEY, remote_task_id, model_id)
    normalized = normalize_status(str(result.get("status") or ""))
    if result.get("video_url"):
        local_status: Literal["queued", "running", "succeeded", "failed"] = "succeeded"
    elif normalized in {"failed", "error", "cancelled", "canceled", "expired"}:
        local_status = "failed"
    else:
        local_status = "running"

    if local_task:
        update_task(
            local_task.id,
            local_status,
            {
                **local_task.result,
                "task_id": remote_task_id,
                "video_url": result.get("video_url"),
                "task_status": result.get("status"),
                "query_response": result.get("provider_response"),
                "query_payload": result.get("query_payload"),
            },
            None if local_status != "failed" else json.dumps(result.get("query_payload") or result.get("provider_response"), ensure_ascii=False)[:1200],
        )

    return {
        "local_task_id": local_task.id if local_task else None,
        "remote_task_id": remote_task_id,
        **result,
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
