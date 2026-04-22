#!/usr/bin/env python3
"""
弹性多模型路由模块

根据智能体名称路由到不同的 LLM 后端（OpenAI/DeepSeek/Gemini）。
借鉴 Claude Code 的工程实践：
- 指数退避重试（transient HTTP errors: 429, 500, 502, 503）
- 断路器模式（连续失败 N 次后短路，避免雪崩）
- 可配置的 per-agent 超时
- provider 降级链（primary → fallback provider）
"""

import os
import json
import time
import logging
import requests
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

from log_config import get_logger

logger = get_logger(__name__)

RETRYABLE_STATUS_CODES = {429, 500, 502, 503}
DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT = 120
CIRCUIT_BREAKER_THRESHOLD = 3
CIRCUIT_BREAKER_COOLDOWN = 60


# ============ Circuit Breaker ============

@dataclass
class _CircuitState:
    failures: int = 0
    last_failure: float = 0.0
    is_open: bool = False


_circuits: dict[str, _CircuitState] = {}


def _get_circuit(key: str) -> _CircuitState:
    if key not in _circuits:
        _circuits[key] = _CircuitState()
    return _circuits[key]


def _record_success(key: str):
    circuit = _get_circuit(key)
    circuit.failures = 0
    circuit.is_open = False


def _record_failure(key: str):
    circuit = _get_circuit(key)
    circuit.failures += 1
    circuit.last_failure = time.time()
    if circuit.failures >= CIRCUIT_BREAKER_THRESHOLD:
        circuit.is_open = True
        logger.warning(f"Circuit breaker OPEN for {key} after {circuit.failures} consecutive failures")


def _is_circuit_open(key: str) -> bool:
    circuit = _get_circuit(key)
    if not circuit.is_open:
        return False
    elapsed = time.time() - circuit.last_failure
    if elapsed > CIRCUIT_BREAKER_COOLDOWN:
        circuit.is_open = False
        circuit.failures = 0
        logger.info(f"Circuit breaker HALF-OPEN for {key} (cooldown elapsed)")
        return False
    return True


# ============ Config Loading ============

def load_models_config() -> dict:
    """加载模型路由配置"""
    config_path = Path(__file__).parent.parent / 'config' / 'models.json'
    if not config_path.exists():
        example_path = config_path.with_name('models.example.json')
        raise FileNotFoundError(
            f"模型配置不存在: {config_path}\n"
            f"请复制 {example_path} 为 models.json 并填入 API Key 环境变量"
        )
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _get_agent_config(agent_name: str, config: Optional[dict] = None) -> dict:
    """获取指定智能体的模型配置"""
    if config is None:
        config = load_models_config()
    agents = config.get("agents", {})
    if agent_name in agents:
        return agents[agent_name]
    return config.get("defaults", {})


def _get_api_key(config: dict) -> str:
    """从环境变量获取 API Key"""
    env_var = config.get("api_key_env", "")
    key = os.getenv(env_var, "")
    if not key:
        raise ValueError(f"环境变量 {env_var} 未设置")
    return key


# ============ Low-level API calls ============

def _call_openai_compatible(base_url: str, api_key: str, model: str,
                            system_prompt: str, user_prompt: str,
                            temperature: float = 0.7,
                            timeout: int = DEFAULT_TIMEOUT) -> str:
    """调用 OpenAI 兼容 API（OpenAI / DeepSeek 等）"""
    url = f"{base_url}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": 8192,
    }

    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    response.raise_for_status()
    result = response.json()
    return result["choices"][0]["message"]["content"]


def _call_google(base_url: str, api_key: str, model: str,
                 system_prompt: str, user_prompt: str,
                 temperature: float = 0.7,
                 timeout: int = DEFAULT_TIMEOUT) -> str:
    """调用 Google Gemini API"""
    url = f"{base_url}/models/{model}:generateContent"
    headers = {"Content-Type": "application/json"}
    params = {"key": api_key}

    payload = {
        "contents": [{"parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 8192,
        },
    }
    if system_prompt:
        payload["systemInstruction"] = {
            "parts": [{"text": system_prompt}]
        }

    response = requests.post(url, headers=headers, params=params, json=payload, timeout=timeout)
    response.raise_for_status()
    result = response.json()

    texts = []
    for candidate in result.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            if "text" in part:
                texts.append(part["text"])
    return "\n".join(texts)


def _dispatch(agent_config: dict, system_prompt: str, user_prompt: str,
              temperature: float = 0.7) -> str:
    """Route a single call to the correct provider."""
    provider = agent_config.get("provider", "openai")
    model = agent_config.get("model", "gpt-4o")
    base_url = agent_config.get("base_url", "https://api.openai.com/v1")
    api_key = _get_api_key(agent_config)
    timeout = agent_config.get("timeout", DEFAULT_TIMEOUT)

    if provider == "google":
        return _call_google(base_url, api_key, model, system_prompt, user_prompt, temperature, timeout)
    else:
        return _call_openai_compatible(base_url, api_key, model, system_prompt, user_prompt, temperature, timeout)


# ============ Retry + Circuit Breaker ============

def _call_with_retry(agent_config: dict, system_prompt: str, user_prompt: str,
                     temperature: float = 0.7,
                     max_retries: int = DEFAULT_MAX_RETRIES,
                     circuit_key: str = "") -> str:
    """
    Call an LLM with exponential backoff retry on transient errors.

    Raises the last exception if all retries are exhausted.
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            result = _dispatch(agent_config, system_prompt, user_prompt, temperature)
            if circuit_key:
                _record_success(circuit_key)
            return result

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            last_error = e

            if status in RETRYABLE_STATUS_CODES and attempt < max_retries - 1:
                wait = min(2 ** attempt + 0.5, 30)
                logger.warning(f"HTTP {status} from {circuit_key}, retry {attempt+1}/{max_retries} in {wait:.1f}s")
                time.sleep(wait)
                continue

            if circuit_key:
                _record_failure(circuit_key)
            raise

        except requests.exceptions.Timeout as e:
            last_error = e
            if attempt < max_retries - 1:
                wait = min(2 ** attempt + 1, 30)
                logger.warning(f"Timeout from {circuit_key}, retry {attempt+1}/{max_retries} in {wait:.1f}s")
                time.sleep(wait)
                continue

            if circuit_key:
                _record_failure(circuit_key)
            raise

        except requests.exceptions.ConnectionError as e:
            last_error = e
            if attempt < max_retries - 1:
                wait = min(2 ** attempt + 1, 30)
                logger.warning(f"Connection error from {circuit_key}, retry {attempt+1}/{max_retries} in {wait:.1f}s")
                time.sleep(wait)
                continue

            if circuit_key:
                _record_failure(circuit_key)
            raise

    raise last_error  # type: ignore


# ============ Public API ============

def call_agent(agent_name: str, user_prompt: str,
               system_prompt: str = "",
               temperature: float = 0.7,
               config: Optional[dict] = None) -> str:
    """
    调用指定智能体对应的 LLM（带重试、断路器、降级链）

    Args:
        agent_name: 智能体名称（如 "deep-thinker", "meme-master"）
        user_prompt: 用户/上下文提示
        system_prompt: 系统提示（智能体人格定义）
        temperature: 温度参数
        config: 可选，预加载的配置

    Returns:
        LLM 返回的文本
    """
    agent_config = _get_agent_config(agent_name, config)
    provider = agent_config.get("provider", "openai")
    model = agent_config.get("model", "gpt-4o")
    circuit_key = f"{agent_name}/{provider}/{model}"

    logger.info(f"call_agent: {agent_name} -> {provider}/{model}")

    # Check circuit breaker
    if _is_circuit_open(circuit_key):
        fallback_config = agent_config.get("fallback")
        if fallback_config:
            fb_provider = fallback_config.get("provider", "openai")
            fb_model = fallback_config.get("model", "gpt-4o")
            logger.warning(f"Circuit open for {circuit_key}, using fallback: {fb_provider}/{fb_model}")
            return _call_with_retry(
                fallback_config, system_prompt, user_prompt, temperature,
                circuit_key=f"{agent_name}/{fb_provider}/{fb_model}",
            )
        logger.warning(f"Circuit open for {circuit_key} with no fallback, attempting anyway")

    # Primary call with retry
    try:
        return _call_with_retry(
            agent_config, system_prompt, user_prompt, temperature,
            circuit_key=circuit_key,
        )
    except Exception as primary_error:
        # Try fallback if available
        fallback_config = agent_config.get("fallback")
        if fallback_config:
            fb_provider = fallback_config.get("provider", "openai")
            fb_model = fallback_config.get("model", "gpt-4o")
            logger.warning(f"Primary {circuit_key} failed, trying fallback: {fb_provider}/{fb_model}")
            try:
                return _call_with_retry(
                    fallback_config, system_prompt, user_prompt, temperature,
                    circuit_key=f"{agent_name}/{fb_provider}/{fb_model}",
                )
            except Exception as fallback_error:
                logger.error(f"Fallback also failed for {agent_name}: {fallback_error}")
                raise fallback_error
        raise primary_error


def load_agent_prompt(agent_name: str) -> str:
    """加载智能体的系统提示（从 AGENT.md 文件）"""
    agent_path = Path(__file__).parent.parent / 'agents' / agent_name / 'AGENT.md'
    if agent_path.exists():
        return agent_path.read_text(encoding='utf-8')

    skill_path = Path(__file__).parent.parent / '.cursor' / 'skills' / agent_name / 'SKILL.md'
    if skill_path.exists():
        return skill_path.read_text(encoding='utf-8')

    raise FileNotFoundError(f"未找到智能体定义: {agent_name}")


def list_available_agents() -> list[str]:
    """列出所有可用的智能体"""
    agents_dir = Path(__file__).parent.parent / 'agents'
    agents = []
    if agents_dir.exists():
        for d in agents_dir.iterdir():
            if d.is_dir() and (d / 'AGENT.md').exists():
                agents.append(d.name)
    return sorted(agents)


def reset_circuits():
    """Reset all circuit breaker states (for testing)."""
    _circuits.clear()


if __name__ == "__main__":
    from log_config import setup_logging
    from compat import ensure_utf8_env, get_platform_info

    ensure_utf8_env()
    setup_logging()
    logger.info("Platform: %s", get_platform_info())

    logger.info("可用智能体:")
    for name in list_available_agents():
        logger.info("  - %s", name)

    logger.info("配置示例: config/models.example.json")
    logger.info("使用: 复制为 config/models.json 并配置环境变量")
    logger.info("断路器状态:")
    if not _circuits:
        logger.info("  (无)")
    for key, state in _circuits.items():
        logger.info("  %s: failures=%d, open=%s", key, state.failures, state.is_open)
