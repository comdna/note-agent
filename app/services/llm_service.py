import os
import json
import requests
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 从环境变量获取 API key
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

def call_llm(messages, temperature=0.7, max_tokens=2000):
    """
    调用 DeepSeek LLM API（非流式）
    
    Args:
        messages: 消息列表，格式为 [{"role": "user/assistant/system", "content": "..."}]
        temperature: 温度参数，控制随机性
        max_tokens: 最大生成 token 数
    
    Returns:
        生成的文本内容
    """
    if not DEEPSEEK_API_KEY:
        raise ValueError("DEEPSEEK_API_KEY 未设置，请检查 .env 文件")
    
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "deepseek-reasoner",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    
    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        
        result = response.json()
        return result['choices'][0]['message']['content']
    
    except requests.exceptions.RequestException as e:
        print(f"LLM API 调用失败: {e}")
        return None


def call_llm_stream(messages, temperature=0.7, max_tokens=2000):
    """
    调用 DeepSeek LLM API（流式输出）
    
    Args:
        messages: 消息列表
        temperature: 温度参数
        max_tokens: 最大生成 token 数
    
    Yields:
        内容片段（字符串）
    """
    if not DEEPSEEK_API_KEY:
        raise ValueError("DEEPSEEK_API_KEY 未设置，请检查 .env 文件")
    
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "deepseek-reasoner",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True
    }
    
    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, stream=True, timeout=120)
        response.raise_for_status()
        
        for line in response.iter_lines():
            if line:
                line_text = line.decode('utf-8')
                # SSE 格式：data: {...}
                if line_text.startswith('data: '):
                    json_str = line_text[6:]  # 去掉 'data: ' 前缀
                    if json_str.strip() == '[DONE]':
                        break
                    try:
                        data = json.loads(json_str)
                        delta = data.get('choices', [{}])[0].get('delta', {})
                        content = delta.get('content', '')
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
    
    except requests.exceptions.RequestException as e:
        print(f"LLM 流式 API 调用失败: {e}")
        yield f"\n[错误: {e}]\n"

def chat_with_context(system_prompt, user_message, context=None, history=None, stream=False):
    """
    带上下文的对话
    
    Args:
        system_prompt: 系统提示词
        user_message: 用户消息
        context: 相关上下文（如知识库内容）
        history: 历史对话记录
        stream: 是否流式输出
    
    Returns:
        AI 回复内容（非流式）或 生成器（流式）
    """
    messages = [
        {"role": "system", "content": system_prompt}
    ]
    
    # 添加历史对话
    if history:
        for msg in history:
            messages.append({
                "role": msg['role'],
                "content": msg['content']
            })
    
    # 添加上下文
    if context:
        user_message = f"参考资料：\n{context}\n\n用户问题：{user_message}"
    
    messages.append({"role": "user", "content": user_message})
    
    if stream:
        return call_llm_stream(messages)
    return call_llm(messages)

def generate_note(title, content_hint, style="学术"):
    """
    生成笔记内容
    
    Args:
        title: 笔记标题
        content_hint: 内容提示
        style: 笔记风格（学术、简洁、详细等）
    
    Returns:
        生成的笔记内容（Markdown 格式）
    """
    system_prompt = f"""你是一个专业的笔记助手，擅长生成结构清晰、内容丰富的笔记。
请用{style}风格撰写笔记，使用 Markdown 格式，包含：
- 清晰的标题层级
- 要点列表
- 必要的代码块或引用
- 总结部分"""

    user_message = f"请帮我写一篇关于「{title}」的笔记。\n\n内容要求：{content_hint}"
    
    return call_llm([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ])

def edit_note(original_content, edit_instruction):
    """
    编辑笔记内容
    
    Args:
        original_content: 原始笔记内容
        edit_instruction: 编辑指令
    
    Returns:
        编辑后的笔记内容
    """
    system_prompt = """你是一个专业的笔记编辑助手。
请根据用户的编辑指令修改笔记内容。
保持原有的 Markdown 格式和结构风格。
只输出修改后的完整内容，不要添加额外说明。"""

    user_message = f"""原始笔记内容：
```
{original_content}
```

编辑要求：{edit_instruction}

请输出修改后的完整笔记内容："""

    return call_llm([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ])

def generate_summary(content):
    """
    生成内容摘要
    
    Args:
        content: 需要摘要的内容
    
    Returns:
        摘要内容
    """
    system_prompt = """你是一个专业的学习助手，擅长总结和提炼知识要点。
请生成结构清晰的摘要，包含：
- 核心概念
- 关键要点
- 重要结论"""

    user_message = f"请为以下内容生成学习摘要：\n\n{content}"
    
    return call_llm([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ])

def generate_outline(topic, depth=2):
    """
    生成学习大纲
    
    Args:
        topic: 主题
        depth: 大纲深度
    
    Returns:
        大纲内容（Markdown 格式）
    """
    system_prompt = """你是一个专业的学习规划助手。
请生成结构清晰的学习大纲，使用 Markdown 格式。
每个章节下包含简要说明。"""

    user_message = f"请为「{topic}」生成一个学习大纲，深度为{depth}级标题。"
    
    return call_llm([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ])

def generate_flashcards(content, count=5):
    """
    生成学习卡片
    
    Args:
        content: 内容
        count: 卡片数量
    
    Returns:
        JSON 格式的卡片列表
    """
    system_prompt = f"""你是一个专业的学习助手，擅长制作学习卡片。
请根据内容生成 {count} 张学习卡片。
每张卡片包含 question（问题）和 answer（答案）两个字段。
只输出 JSON 数组格式，不要添加其他内容。
示例格式：
[
  {{"question": "问题1", "answer": "答案1"}},
  {{"question": "问题2", "answer": "答案2"}}
]"""

    user_message = f"请为以下内容生成学习卡片：\n\n{content}"
    
    result = call_llm([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ])
    
    # 尝试解析 JSON
    try:
        # 去除可能的 markdown 代码块标记
        if result.startswith('```'):
            result = result.split('\n', 1)[1]  # 去除第一行
            result = result.rsplit('\n', 1)[0]  # 去除最后一行
        
        return json.loads(result)
    except json.JSONDecodeError:
        # 如果解析失败，返回空列表
        print(f"JSON 解析失败: {result}")
        return []

def generate_quiz(content, count=5):
    """
    生成练习题
    
    Args:
        content: 内容
        count: 题目数量
    
    Returns:
        Markdown 格式的练习题
    """
    system_prompt = f"""你是一个专业的教育助手，擅长出题。
请根据内容生成 {count} 道练习题，包含：
- 选择题
- 简答题
使用 Markdown 格式，包含答案和解析。"""

    user_message = f"请为以下内容生成练习题：\n\n{content}"
    
    return call_llm([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ])

def generate_glossary(content):
    """
    生成术语表
    
    Args:
        content: 内容
    
    Returns:
        Markdown 格式的术语表
    """
    system_prompt = """你是一个专业的知识整理助手。
请从内容中提取专业术语，生成术语表。
使用 Markdown 表格格式，包含术语和解释两列。"""

    user_message = f"请从以下内容中提取术语并生成术语表：\n\n{content}"
    
    return call_llm([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ])

def answer_question(question, context=None, history=None):
    """
    回答问题
    
    Args:
        question: 用户问题
        context: 相关上下文
        history: 历史对话
    
    Returns:
        回答内容
    """
    system_prompt = """你是一个专业的学习助手，请根据用户的问题提供准确、有帮助的回答。
如果提供了参考资料，请基于资料回答并注明来源。
回答要结构清晰，必要时使用 Markdown 格式。"""

    return chat_with_context(system_prompt, question, context, history)


def answer_with_context(question: str, context: str, history=None):
    """
    基于知识库上下文回答问题
    
    Args:
        question: 用户问题
        context: 从知识库检索到的相关内容
        history: 历史对话
    
    Returns:
        回答内容
    """
    system_prompt = """你是一个专业的学习助手，正在基于用户上传的学习资料回答问题。

请遵循以下规则：
1. 基于提供的参考资料回答问题
2. 如果参考资料中有相关信息，请明确指出来源（文档名和页码）
3. 如果参考资料不足以回答问题，请坦诚说明
4. 回答要准确、简洁、有条理
5. 必要时使用 Markdown 格式增强可读性

参考资料格式：[来源: 文档名 第X页]"""

    user_message = f"""参考资料：
{context}

用户问题：{question}

请基于参考资料回答问题，并注明来源。"""

    return chat_with_context(system_prompt, user_message, None, history)
