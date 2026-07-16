# -*- coding: utf-8 -*-
"""
AI 客户端统一封装
支持 OpenRouter / 阿里云 等多渠道切换
"""
import os
import yaml
import requests
from typing import List, Dict, Optional
from utils.paths import config_path as get_config_path


class AIClient:
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = get_config_path("settings.yaml")
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        
        self.api_cfg = cfg.get("api", {})
        self._setup_provider()
    
    def _setup_provider(self):
        """选择可用 provider，优先 OpenRouter"""
        or_cfg = self.api_cfg.get("openrouter", {})
        if or_cfg.get("api_key"):
            self.provider = "openrouter"
            self.base_url = or_cfg["base_url"].rstrip("/")
            self.api_key = or_cfg["api_key"]
            self.model = or_cfg.get("model", "qwen/qwen-3-235b-a22b:free")
            self.fallback_model = or_cfg.get("fallback_model")
        else:
            ali_cfg = self.api_cfg.get("aliyun", {})
            self.provider = "aliyun"
            self.base_url = ali_cfg.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
            self.api_key = ali_cfg.get("api_key", "")
            self.model = ali_cfg.get("model", "qwen-max-latest")
            self.fallback_model = None
    
    def chat(self, 
             messages: List[Dict[str, str]], 
             model: Optional[str] = None,
             temperature: float = 0.7,
             max_tokens: int = 4000) -> str:
        """
        调用 AI 聊天接口
        messages: [{"role": "system"/"user"/"assistant", "content": "..."}]
        """
        if not self.api_key:
            raise RuntimeError("AI API Key 未配置。请在 config/settings.yaml 中填写 openrouter.api_key 或 aliyun.api_key")
        
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        if self.provider == "openrouter":
            headers["HTTP-Referer"] = "https://meituan.com"
            headers["X-Title"] = "SocialMediaMarketing"
        
        payload = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            if self.fallback_model and not model:
                print(f"[AIClient] 主模型失败，尝试 fallback: {self.fallback_model}")
                return self.chat(messages, model=self.fallback_model, temperature=temperature, max_tokens=max_tokens)
            raise RuntimeError(f"AI API 调用失败: {e}")
    
    def generate_content(self, 
                         prompt: str, 
                         system_prompt: Optional[str] = None,
                         **kwargs) -> str:
        """便捷方法：直接通过 prompt 生成内容"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages, **kwargs)


# 单例
_ai_client = None

def get_ai_client() -> AIClient:
    global _ai_client
    if _ai_client is None:
        _ai_client = AIClient()
    return _ai_client
