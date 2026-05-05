"""统一的 LLM 调用客户端模块。

支持 DeepSeek、Qwen、OpenAI 三种模型提供商，通过环境变量切换。
使用 httpx 直接调用 OpenAI 典范 API，不依赖 openai SDK。

Example:
    >>> from pipeline.model_client import quick_chat
    >>> response = quick_chat("你好，请介绍一下自己")
    >>> print(response.content)
"""

import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

# 模型提供商配置
PROVIDER_CONFIGS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-v4-flash",
        "pricing": {
            "deepseek-v4-flash": {"input": 0.14, "output": 0.28},
            "deepseek-v4-pro": {"input": 0.50, "output": 1.50},
        },
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key_env": "QWEN_API_KEY",
        "default_model": "qwen-turbo",
        "pricing": {
            "qwen-turbo": {"input": 0.02, "output": 0.06},
            "qwen-plus": {"input": 0.04, "output": 0.12},
            "qwen-max": {"input": 0.12, "output": 0.36},
        },
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "default_model": "gpt-4o-mini",
        "pricing": {
            "gpt-4o-mini": {"input": 0.15, "output": 0.60},
            "gpt-4o": {"input": 5.00, "output": 15.00},
            "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
        },
    },
}

# 重试配置
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # 秒
REQUEST_TIMEOUT = 60.0  # 秒


@dataclass
class Usage:
    """Token 用量统计。

    Attributes:
        prompt_tokens: 输入 token 数量。
        completion_tokens: 输出 token 数量。
        total_tokens: 总 token 数量。
    """

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class LLMResponse:
    """LLM 调用响应。

    Attributes:
        content: 模型生成的文本内容。
        usage: Token 用量统计。
        model: 实际使用的模型名称。
        provider: 模型提供商名称。
    """

    content: str
    usage: Usage
    model: str
    provider: str


class LLMProvider(ABC):
    """LLM 提供商抽象基类。"""

    @abstractmethod
    def chat(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        """发送对话请求。

        Args:
            prompt: 用户输入的提示词。
            system_prompt: 系统提示词。
            temperature: 生成温度，控制随机性。
            max_tokens: 最大生成 token 数。

        Returns:
            LLMResponse 对象，包含生成内容和用量统计。

        Raises:
            httpx.HTTPStatusError: HTTP 请求失败。
            httpx.TimeoutException: 请求超时。
        """
        pass


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI 兼容 API 提供商实现。

    支持 DeepSeek、Qwen、OpenAI 等兼容 OpenAI API 格式的提供商。

    Attributes:
        provider_name: 提供商名称。
        base_url: API 基础 URL。
        api_key: API 密钥。
        model: 模型名称。
    """

    def __init__(
        self,
        provider_name: str,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        """初始化提供商。

        Args:
            provider_name: 提供商名称（deepseek/qwen/openai）。
            api_key: API 密钥，若不提供则从环境变量读取。
            model: 模型名称，若不提供则使用默认模型。
            base_url: API 基础 URL，若不提供则使用默认值。

        Raises:
            ValueError: 提供商名称不支持或 API 密钥未配置。
        """
        if provider_name not in PROVIDER_CONFIGS:
            raise ValueError(
                f"不支持的提供商: {provider_name}，"
                f"可选: {list(PROVIDER_CONFIGS.keys())}"
            )

        config = PROVIDER_CONFIGS[provider_name]
        self.provider_name = provider_name
        self.base_url = base_url or config["base_url"]
        self.model = model or config["default_model"]
        self._pricing = config["pricing"]

        env_key = config["api_key_env"]
        self.api_key = api_key or os.getenv(env_key)
        if not self.api_key:
            raise ValueError(
                f"未配置 API 密钥，请设置环境变量 {env_key} 或直接传入 api_key"
            )

        logger.info(
            "初始化 %s 提供商，模型: %s", provider_name, self.model
        )

    def chat(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        """发送对话请求。

        Args:
            prompt: 用户输入的提示词。
            system_prompt: 系统提示词。
            temperature: 生成温度，控制随机性。
            max_tokens: 最大生成 token 数。

        Returns:
            LLMResponse 对象，包含生成内容和用量统计。

        Raises:
            httpx.HTTPStatusError: HTTP 请求失败。
            httpx.TimeoutException: 请求超时。
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        logger.debug("发送请求到 %s，模型: %s", self.provider_name, self.model)

        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()

        data = response.json()
        choice = data["choices"][0]
        usage_data = data.get("usage", {})

        usage = Usage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )

        result = LLMResponse(
            content=choice["message"]["content"],
            usage=usage,
            model=data.get("model", self.model),
            provider=self.provider_name,
        )

        logger.info(
            "请求完成，消耗 tokens: %d (输入: %d, 输出: %d)",
            usage.total_tokens,
            usage.prompt_tokens,
            usage.completion_tokens,
        )

        return result


def get_provider(
    provider_name: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> OpenAICompatibleProvider:
    """获取 LLM 提供商实例。

    Args:
        provider_name: 提供商名称，默认从环境变量 LLM_PROVIDER 读取。
        api_key: API 密钥，默认从对应环境变量读取。
        model: 模型名称，默认使用提供商默认模型。

    Returns:
        OpenAICompatibleProvider 实例。
    """
    name = provider_name or os.getenv("LLM_PROVIDER", "deepseek")
    return OpenAICompatibleProvider(
        provider_name=name, api_key=api_key, model=model
    )


def chat_with_retry(
    prompt: str,
    system_prompt: Optional[str] = None,
    provider: Optional[OpenAICompatibleProvider] = None,
    max_retries: int = MAX_RETRIES,
    temperature: float = 0.7,
    max_tokens: int = 2000,
) -> LLMResponse:
    """带重试的对话请求。

    使用指数退避策略进行重试，最多重试指定次数。

    Args:
        prompt: 用户输入的提示词。
        system_prompt: 系统提示词。
        provider: LLM 提供商实例，若不提供则自动创建。
        max_retries: 最大重试次数。
        temperature: 生成温度。
        max_tokens: 最大生成 token 数。

    Returns:
        LLMResponse 对象。

    Raises:
        httpx.HTTPStatusError: 重试耗尽后仍然失败。
        httpx.TimeoutException: 重试耗尽后仍然超时。
    """
    if provider is None:
        provider = get_provider()

    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return provider.chat(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except (httpx.HTTPStatusError, httpx.TimeoutException) as exc:
            last_exception = exc
            if attempt < max_retries:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "请求失败 (尝试 %d/%d)，%s 后重试: %s",
                    attempt + 1,
                    max_retries + 1,
                    f"{delay:.1f}秒",
                    str(exc),
                )
                time.sleep(delay)
            else:
                logger.error(
                    "请求失败，已用尽 %d 次重试: %s",
                    max_retries + 1,
                    str(exc),
                )

    raise last_exception  # type: ignore[misc]


def estimate_tokens(text: str) -> int:
    """估算文本的 token 数量。

    使用简化的估算方法：英文约 4 字符/token，中文约 2 字符/token。

    Args:
        text: 需要估算的文本。

    Returns:
        估算的 token 数量。
    """
    chinese_chars = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    other_chars = len(text) - chinese_chars
    return chinese_chars // 2 + other_chars // 4


def calculate_cost(
    usage: Usage,
    provider_name: str,
    model: str,
) -> float:
    """计算 API 调用成本。

    Args:
        usage: Token 用量统计。
        provider_name: 提供商名称。
        model: 模型名称。

    Returns:
        成本金额（USD）。

    Raises:
        ValueError: 找不到对应模型的定价信息。
    """
    config = PROVIDER_CONFIGS.get(provider_name)
    if not config:
        raise ValueError(f"未知提供商: {provider_name}")

    pricing = config["pricing"].get(model)
    if not pricing:
        raise ValueError(
            f"找不到模型 {model} 的定价信息，"
            f"可用模型: {list(config['pricing'].keys())}"
        )

    input_cost = (usage.prompt_tokens / 1000) * pricing["input"]
    output_cost = (usage.completion_tokens / 1000) * pricing["output"]

    return input_cost + output_cost


def quick_chat(
    prompt: str,
    system_prompt: str = "你是一个有帮助的AI助手。",
    provider_name: Optional[str] = None,
) -> str:
    """便捷的快速对话函数。

    一句话调用 LLM，返回文本内容。

    Args:
        prompt: 用户输入的提示词。
        system_prompt: 系统提示词，默认为通用助手。
        provider_name: 提供商名称，默认从环境变量读取。

    Returns:
        模型生成的文本内容。

    Example:
        >>> answer = quick_chat("什么是机器学习？")
        >>> print(answer)
    """
    provider = get_provider(provider_name=provider_name)
    response = chat_with_retry(
        prompt=prompt,
        system_prompt=system_prompt,
        provider=provider,
    )
    return response.content


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    print("=" * 60)
    print("LLM 客户端测试")
    print("=" * 60)

    # 测试提供商初始化
    print("\n1. 测试提供商初始化")
    try:
        provider = get_provider()
        print(f"   提供商: {provider.provider_name}")
        print(f"   模型: {provider.model}")
        print(f"   Base URL: {provider.base_url}")
    except ValueError as exc:
        print(f"   初始化失败: {exc}")
        print("   请设置环境变量 LLM_PROVIDER 和对应的 API_KEY")
        print("   示例: export LLM_PROVIDER=deepseek")
        print("   示例: export DEEPSEEK_API_KEY=your_key")

    # 测试 token 估算
    print("\n2. 测试 Token 估算")
    test_text = "你好，这是一段测试文本。Hello, this is a test."
    estimated = estimate_tokens(test_text)
    print(f"   文本: {test_text}")
    print(f"   估算 token 数: {estimated}")

    # 测试对话请求
    print("\n3. 测试对话请求")
    try:
        response = chat_with_retry(
            prompt="用一句话介绍什么是大语言模型。",
            system_prompt="你是一个技术专家，请简洁回答。",
        )
        print(f"   回复: {response.content}")
        print(f"   模型: {response.model}")
        print(f"   Token 用量: {response.usage.total_tokens}")

        # 计算成本
        cost = calculate_cost(
            usage=response.usage,
            provider_name=response.provider,
            model=response.model,
        )
        print(f"   本次调用成本: ${cost:.6f}")
    except ValueError as exc:
        print(f"   请求失败（配置错误）: {exc}")
    except (httpx.HTTPStatusError, httpx.TimeoutException) as exc:
        print(f"   请求失败（网络错误）: {exc}")

    # 测试便捷函数
    print("\n4. 测试便捷函数 quick_chat()")
    try:
        answer = quick_chat("1+1等于几？")
        print(f"   回复: {answer}")
    except (ValueError, httpx.HTTPStatusError, httpx.TimeoutException) as exc:
        print(f"   请求失败: {exc}")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
