import json
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from app.services import project_service, file_service, kb_service, llm_service, agent_service

DATA_DIR = None
CHAT_MEMORY_ROUNDS = 5
CHAT_MEMORY_MESSAGES = CHAT_MEMORY_ROUNDS * 2


def _get_recent_history(messages: Optional[List[Dict]]) -> List[Dict]:
    if not messages:
        return []
    return messages[-CHAT_MEMORY_MESSAGES:]

def init_data_dir(data_dir):
    global DATA_DIR
    DATA_DIR = data_dir
    os.makedirs(DATA_DIR, exist_ok=True)

def extract_filename_from_text(content: str) -> Optional[str]:
    """从用户输入中提取可能的文件名（普通文件）"""
    if not content:
        return None
    import re
    match = re.search(r'([\w\-]+\.(txt|md|markdown|json|py|js|html|css))', content, re.IGNORECASE)
    if match:
        return match.group(1)
    return None

def has_kb_keywords(content: str) -> bool:
    """判断是否明确指向知识库/PDF"""
    if not content:
        return False
    content_lower = content.lower()
    kb_keywords = [
        '知识库', 'pdf', '文档', '资料', '论文', '课件', '教材', '书籍', '书本',
        'in the document', 'in the pdf', 'which page'
    ]
    return any(k in content_lower for k in kb_keywords)

    file_hint = extract_filename_from_text(content)
    intent_labels = [
        "CREATE_NOTE",
        "EDIT_FILE",
        "SEARCH_KB",
        "WEB_SEARCH",
        "GENERATE_SUMMARY",
    ]

    system_prompt = "You are an intent classifier. Select exactly one label from the provided list and output only the label."

    history_text = ""
    if history:
        for msg in history[-CHAT_MEMORY_MESSAGES:]:
            role = "user" if msg.get('role') == 'user' else "assistant"
            history_text += f"{role}: {msg.get('content', '')[:100]}...\n"

    user_prompt = (
        "Choose one label from below:\n\n"
        + "\n".join(intent_labels)
        + f"\n\nUser input:\n\"{content}\"\n\nOutput:"
    )
    if history_text:
        user_prompt = f"History:\n{history_text}\n\n" + user_prompt

    label_map = {
        "CREATE_NOTE": "CREATE_NOTE",
        "EDIT_FILE": "EDIT_NOTE",
        "SEARCH_KB": "QUERY_KB",
        "WEB_SEARCH": "WEB_SEARCH",
        "GENERATE_SUMMARY": "GENERATE_SUMMARY",
    }

    try:
        result = llm_service.call_llm(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=20,
        )
        if result:
            label = result.strip().upper().replace("`", "").replace('"', "")
            if label in label_map:
                mapped_intent = label_map[label]
                needs_kb = mapped_intent == "QUERY_KB"
                if mapped_intent == "GENERATE_SUMMARY" and not file_hint:
                    needs_kb = True
                return {
                    'intent': mapped_intent,
                    'confidence': 0.8,
                    'reasoning': f'LLM classified as {label}',
                    'needs_kb': needs_kb,
                    'target_file': file_hint,
                    'parameters': {'raw_label': label}
                }
    except Exception as e:
        print(f"LLM intent detection failed: {e}")

    return fallback_intent_detection(content)

    content_lower = content.lower()
    kb_keywords = [
        '知识库', 'pdf', '文档', '资料', '论文', '课件', '教材', '书籍', '书本',
        'in the document', 'in the pdf', 'which page'
    ]
    return any(k in content_lower for k in kb_keywords)

def match_file_from_content(project_id: str, content: str) -> tuple[Optional[Dict], List[Dict]]:
    """从内容中匹配普通文件名，返回唯一匹配文件或候选列表"""
    if not content:
        return None, []
    content_lower = content.lower()
    files = file_service.list_files(project_id)

    # 优先匹配带扩展名的文件名
    explicit = extract_filename_from_text(content)
    if explicit:
        file_data = get_file_data_by_name_or_id(project_id, explicit)
        if file_data:
            return file_data, []

    matches = []
    for f in files:
        name = f.get('name', '')
        if not name:
            continue
        name_lower = name.lower()
        base = name_lower.rsplit('.', 1)[0]
        if name_lower and name_lower in content_lower:
            matches.append(f)
        elif base and len(base) >= 2 and base in content_lower:
            matches.append(f)

    if len(matches) == 1:
        file_data = file_service.get_file(project_id, matches[0]['id'])
        return file_data, []
    return None, matches

def get_file_data_by_name_or_id(project_id: str, target_file: str) -> Optional[Dict]:
    """按名称或ID查找普通文件并返回完整数据"""
    if not target_file:
        return None
    files = file_service.list_files(project_id)
    for f in files:
        if f.get('name') == target_file or f.get('id') == target_file:
            return file_service.get_file(project_id, f['id'])
    return None


def _normalize_background_file_ids(file_ids: Optional[List[str]]) -> List[str]:
    if not file_ids:
        return []
    normalized = []
    seen = set()
    for file_id in file_ids:
        if not isinstance(file_id, str):
            continue
        file_id = file_id.strip()
        if not file_id or file_id in seen:
            continue
        seen.add(file_id)
        normalized.append(file_id)
    return normalized


def _build_background_context(project_id: str, file_ids: Optional[List[str]]) -> tuple[str, List[Dict], List[str]]:
    selected_ids = _normalize_background_file_ids(file_ids)
    if not selected_ids:
        return "", [], []

    context_parts = []
    citations = []
    valid_ids = []

    for file_id in selected_ids:
        file_data = file_service.get_file(project_id, file_id)
        if not file_data:
            continue
        if file_data.get('is_kb_file'):
            continue
        if file_data.get('type') != 'text':
            continue

        file_content = file_data.get('content') or ''
        if not file_content:
            continue

        file_name = file_data.get('name') or file_id
        valid_ids.append(file_id)
        context_parts.append(f"[Background File: {file_name}]\n{file_content[:4000]}")
        citations.append({'source': file_name, 'page': 1})

    return "\n\n---\n\n".join(context_parts), citations, valid_ids


def list_chats(project_id):
    """获取项目会话列表"""
    projects = project_service.load_projects()
    if project_id not in projects:
        return []
    
    chats = projects[project_id].get('chats', {})
    result = []
    for cid, chat in chats.items():
        result.append({
            'id': cid,
            'title': chat.get('title'),
            'created_at': chat.get('created_at'),
            'updated_at': chat.get('updated_at')
        })
    return sorted(result, key=lambda x: x['updated_at'], reverse=True)


def create_chat(project_id, title):
    """创建新会话"""
    projects = project_service.load_projects()
    if project_id not in projects:
        return None
    
    chat_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()
    
    chat = {
        'id': chat_id,
        'title': title,
        'messages': [],
        'background_file_ids': [],
        'proposals': {},
        'created_at': now,
        'updated_at': now
    }
    
    if 'chats' not in projects[project_id]:
        projects[project_id]['chats'] = {}
    
    projects[project_id]['chats'][chat_id] = chat
    projects[project_id]['updated_at'] = now
    project_service.save_projects(projects)
    
    return {
        'id': chat_id,
        'title': title,
        'background_file_ids': [],
        'created_at': now,
        'updated_at': now
    }


def get_chat(project_id, chat_id):
    """获取会话详情"""
    projects = project_service.load_projects()
    if project_id not in projects:
        return None
    
    chats = projects[project_id].get('chats', {})
    if chat_id not in chats:
        return None
    
    chat = chats[chat_id]
    return {
        'id': chat_id,
        'title': chat.get('title'),
        'messages': chat.get('messages', []),
        'background_file_ids': chat.get('background_file_ids', []),
        'created_at': chat.get('created_at'),
        'updated_at': chat.get('updated_at')
    }


def delete_chat(project_id, chat_id):
    """删除会话"""
    projects = project_service.load_projects()
    if project_id not in projects:
        return False
    
    chats = projects[project_id].get('chats', {})
    if chat_id not in chats:
        return False
    
    del projects[project_id]['chats'][chat_id]
    projects[project_id]['updated_at'] = datetime.now().isoformat()
    project_service.save_projects(projects)
    return True


def set_chat_background_files(project_id: str, chat_id: str, file_ids: Optional[List[str]]):
    projects = project_service.load_projects()
    if project_id not in projects:
        return None

    chats = projects[project_id].get('chats', {})
    if chat_id not in chats:
        return None

    normalized_ids = _normalize_background_file_ids(file_ids)
    _, _, valid_ids = _build_background_context(project_id, normalized_ids)

    now = datetime.now().isoformat()
    chats[chat_id]['background_file_ids'] = valid_ids
    chats[chat_id]['updated_at'] = now
    projects[project_id]['updated_at'] = now
    project_service.save_projects(projects)

    return {'background_file_ids': valid_ids}


def analyze_intent_with_llm(content: str, history: list = None) -> dict:
    """
    使用LLM进行意图识别，更准确地判断用户需要什么
    
    返回: {
        'intent': 'QUERY_KB' | 'READ_FILE' | 'CREATE_NOTE' | 'EDIT_NOTE' | 'DELETE_NOTE' | 
                  'GENERATE_SUMMARY' | 'GENERATE_OUTLINE' | 'GENERATE_FLASHCARDS' | 
                  'GENERATE_QUIZ' | 'GENERATE_GLOSSARY' | 'WEB_SEARCH' | 'GENERAL_CHAT',
        'confidence': float,
        'reasoning': str,
        'needs_kb': bool,
        'target_file': str | None,  # 如果要读取特定文件
        'parameters': dict  # 其他参数
    }
    """
    # 首先检查明显的关键词触发
    file_hint = extract_filename_from_text(content)
    intent_labels = [
        "CREATE_NOTE",
        "EDIT_FILE",
        "SEARCH_KB",
        "WEB_SEARCH",
        "GENERATE_SUMMARY",
    ]

    system_prompt = "You are an intent classifier. Select exactly one label from the provided list and output only the label."

    history_text = ""
    if history:
        for msg in history[-CHAT_MEMORY_MESSAGES:]:
            role = "user" if msg.get('role') == 'user' else "assistant"
            history_text += f"{role}: {msg.get('content', '')[:100]}...\n"

    user_prompt = (
        "Choose one label from below:\n\n"
        + "\n".join(intent_labels)
        + f"\n\nUser input:\n\"{content}\"\n\nOutput:"
    )
    if history_text:
        user_prompt = f"History:\n{history_text}\n\n" + user_prompt

    label_map = {
        "CREATE_NOTE": "CREATE_NOTE",
        "EDIT_FILE": "EDIT_NOTE",
        "SEARCH_KB": "QUERY_KB",
        "WEB_SEARCH": "WEB_SEARCH",
        "GENERATE_SUMMARY": "GENERATE_SUMMARY",
    }

    try:
        result = llm_service.call_llm(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=20,
        )
        if result:
            label = result.strip().upper().replace("`", "").replace('"', "")
            if label in label_map:
                mapped_intent = label_map[label]
                needs_kb = mapped_intent == "QUERY_KB"
                if mapped_intent == "GENERATE_SUMMARY" and not file_hint:
                    needs_kb = True
                return {
                    'intent': mapped_intent,
                    'confidence': 0.8,
                    'reasoning': f'LLM classified as {label}',
                    'needs_kb': needs_kb,
                    'target_file': file_hint,
                    'parameters': {'raw_label': label}
                }
    except Exception as e:
        print(f"LLM intent detection failed: {e}")

    return fallback_intent_detection(content)

    content_lower = content.lower()
    file_hint = extract_filename_from_text(content)
    
    # 明显的创建/编辑/删除意图
    if any(kw in content_lower for kw in ['创建笔记', '新建笔记', '写一篇', '帮我写']):
        return {'intent': 'CREATE_NOTE', 'confidence': 0.9, 'reasoning': '明确创建笔记指令', 'needs_kb': False, 'target_file': None, 'parameters': {}}
    if any(kw in content_lower for kw in ['修改笔记', '改一下', '编辑笔记']):
        return {'intent': 'EDIT_NOTE', 'confidence': 0.9, 'reasoning': '明确修改笔记指令', 'needs_kb': False, 'target_file': None, 'parameters': {}}
    if any(kw in content_lower for kw in ['删除笔记', '删掉笔记']):
        return {'intent': 'DELETE_NOTE', 'confidence': 0.9, 'reasoning': '明确删除笔记指令', 'needs_kb': False, 'target_file': None, 'parameters': {}}
    
    # 明显的生成意图
    if any(kw in content_lower for kw in ['总结', '摘要', '概括']):
        return {
            'intent': 'GENERATE_SUMMARY',
            'confidence': 0.85,
            'reasoning': '生成摘要指令',
            'needs_kb': False if file_hint else True,
            'target_file': file_hint,
            'parameters': {}
        }
    if any(kw in content_lower for kw in ['大纲', '目录结构']):
        return {
            'intent': 'GENERATE_OUTLINE',
            'confidence': 0.85,
            'reasoning': '生成大纲指令',
            'needs_kb': False if file_hint else True,
            'target_file': file_hint,
            'parameters': {}
        }
    if any(kw in content_lower for kw in ['卡片', '复习卡', 'flashcard']):
        return {
            'intent': 'GENERATE_FLASHCARDS',
            'confidence': 0.85,
            'reasoning': '生成学习卡片指令',
            'needs_kb': False if file_hint else True,
            'target_file': file_hint,
            'parameters': {}
        }
    if any(kw in content_lower for kw in ['练习题', '题目', '测验', 'quiz']):
        return {
            'intent': 'GENERATE_QUIZ',
            'confidence': 0.85,
            'reasoning': '生成练习题指令',
            'needs_kb': False if file_hint else True,
            'target_file': file_hint,
            'parameters': {}
        }
    if any(kw in content_lower for kw in ['术语表', '名词解释', 'glossary']):
        return {
            'intent': 'GENERATE_GLOSSARY',
            'confidence': 0.85,
            'reasoning': '生成术语表指令',
            'needs_kb': False if file_hint else True,
            'target_file': file_hint,
            'parameters': {}
        }
    
    # 明显的搜索意图
    if any(kw in content_lower for kw in ['搜索', '搜一下', '查一下', '网上搜索']):
        return {'intent': 'WEB_SEARCH', 'confidence': 0.85, 'reasoning': '明确要求网络搜索', 'needs_kb': False, 'target_file': None, 'parameters': {}}
    
    # 使用LLM进行更精细的意图识别
    system_prompt = """你是一个意图识别助手。请分析用户输入，判断用户意图。

    可能的意图类型：
    - QUERY_KB: 查询知识库/询问文档内容（如"我的资料里讲了什么"、"PDF中关于XXX的内容"）
    - READ_FILE: 读取特定文件（如"打开note.md"、"读取xxx.txt的内容"）
    - CREATE_NOTE: 创建笔记
    - EDIT_NOTE: 修改笔记  
    - DELETE_NOTE: 删除笔记
    - GENERATE_SUMMARY: 生成摘要
    - GENERATE_OUTLINE: 生成大纲
    - GENERATE_FLASHCARDS: 生成学习卡片
    - GENERATE_QUIZ: 生成练习题
    - GENERATE_GLOSSARY: 生成术语表
    - WEB_SEARCH: 需要网络搜索
    - GENERAL_CHAT: 一般聊天/问候

    返回JSON格式（不要包含markdown代码块标记）：
    {
        "intent": "意图类型",
        "confidence": 0.0-1.0,
        "reasoning": "判断理由",
        "needs_kb": true/false,
        "target_file": "识别到的文件名（如果有）",
        "parameters": {}
    }"""

    # 构建历史上下文
    history_text = ""
    if history and len(history) > 0:
        recent_history = history[-CHAT_MEMORY_MESSAGES:]
        for msg in recent_history:
            role = "用户" if msg.get('role') == 'user' else "助手"
            history_text += f"{role}: {msg.get('content', '')[:100]}...\n"
    
    user_prompt = f"""历史对话：
{history_text}

当前用户输入：{content}

请分析用户意图，返回JSON格式的分析结果。"""

    try:
        result = llm_service.call_llm([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ], temperature=0.1, max_tokens=500)
        
        if result:
            # 清理可能的markdown标记
            result = result.strip()
            if result.startswith('```'):
                result = result.split('\n', 1)[1] if '\n' in result else ''
                result = result.rsplit('\n', 1)[0] if '\n' in result else result
                result = result.replace('```json', '').replace('```', '').strip()
            
            parsed = json.loads(result)
            return {
                'intent': parsed.get('intent', 'GENERAL_CHAT'),
                'confidence': parsed.get('confidence', 0.5),
                'reasoning': parsed.get('reasoning', ''),
                'needs_kb': parsed.get('needs_kb', False),
                'target_file': parsed.get('target_file'),
                'parameters': parsed.get('parameters', {})
            }
    except Exception as e:
        print(f"LLM意图识别失败: {e}")
    
    # 回退到关键词匹配
    return fallback_intent_detection(content)


def fallback_intent_detection(content: str) -> dict:
    """当LLM识别失败时的回退方案"""
    content_lower = content.lower()
    
    # 文件读取意图
    file_patterns = [
        r'(打开|读取|查看|读一下|看看).{0,5}(文件|file|文档)',
        r'(\w+\.(txt|md|json|py|js|html|css))',
        r'(note|file|doc).*?(里面|内容|写了什么)',
    ]
    import re
    for pattern in file_patterns:
        if re.search(pattern, content_lower):
            # 尝试提取文件名
            file_match = re.search(r'([\w\-]+\.(txt|md|json|py|js|html|css))', content_lower)
            target_file = file_match.group(1) if file_match else None
            return {
                'intent': 'READ_FILE',
                'confidence': 0.7,
                'reasoning': '关键词匹配到文件读取意图',
                'needs_kb': False,
                'target_file': target_file,
                'parameters': {}
            }
    
    # 知识库查询意图
    kb_keywords = [
        '文档', '资料', '文件', 'pdf', '论文', '课件', '教材', '书本', '书籍',
        '查找', '搜索', '检索', '查询', '在哪', '哪一页', '第几页',
        '讲什么', '说了什么', '提到', '关于', '内容', '介绍', '解释',
        '根据资料', '根据文档', '我的资料', '我的文档', '上传的', '资料里', '文档中',
        'summary of', 'what does', 'where is', 'which page',
        'in the document', 'in my file', 'in the pdf'
    ]
    for keyword in kb_keywords:
        if keyword in content_lower:
            return {
                'intent': 'QUERY_KB',
                'confidence': 0.75,
                'reasoning': f'关键词匹配: {keyword}',
                'needs_kb': True,
                'target_file': None,
                'parameters': {}
            }
    
    # 疑问词+学习内容 → 可能查询知识库
    question_words = ['什么', '哪些', '怎么', '如何', '为什么', '多少', '谁', '哪里']
    learning_keywords = ['概念', '定义', '原理', '方法', '理论', '技术', '算法']
    if any(w in content_lower for w in question_words) and any(w in content_lower for w in learning_keywords):
        return {
            'intent': 'QUERY_KB',
            'confidence': 0.6,
            'reasoning': '疑问词+学习内容，可能涉及知识库',
            'needs_kb': True,
            'target_file': None,
            'parameters': {}
        }
    
    # 默认一般对话
    return {
        'intent': 'GENERAL_CHAT',
        'confidence': 0.5,
        'reasoning': '未匹配到特定意图',
        'needs_kb': False,
        'target_file': None,
        'parameters': {}
    }


def should_use_knowledge_base(content: str, history: list = None) -> bool:
    """
    判断用户问题是否需要查询本地知识库（使用LLM意图识别）
    """
    intent_result = analyze_intent_with_llm(content, history)
    return intent_result.get('needs_kb', False) or intent_result.get('intent') in ['QUERY_KB', 'READ_FILE']


def send_message(project_id, chat_id, content, use_web=False, background_file_ids=None):
    """???????AI???????"""
    projects = project_service.load_projects()
    if project_id not in projects:
        return None

    chats = projects[project_id].get('chats', {})
    if chat_id not in chats:
        return None

    chat = chats[chat_id]
    if background_file_ids is not None:
        chat['background_file_ids'] = _normalize_background_file_ids(background_file_ids)
    active_background_file_ids = chat.get('background_file_ids', [])
    now = datetime.now().isoformat()

    # ??????
    user_message = {
        'id': str(uuid.uuid4())[:8],
        'role': 'user',
        'content': content,
        'created_at': now
    }
    chat['messages'].append(user_message)

    # ????????????
    history = _get_recent_history(chat.get('messages', []))

    tool_response = agent_service.run_tool_call(project_id, content, history)
    if tool_response:
        response = tool_response
    else:
        # ?????????
        intent_result = analyze_intent_with_llm(content, history)
        intent = intent_result['intent']

        # ?? READ_FILE ??
        if intent == 'READ_FILE' and intent_result.get('target_file'):
            response = generate_file_read_response(project_id, intent_result['target_file'], content)
        else:
            response = generate_response(
                project_id,
                chat,
                content,
                intent,
                use_web,
                intent_result,
                active_background_file_ids,
            )

    # ??AI??
    ai_message = {
        'id': str(uuid.uuid4())[:8],
        'role': 'assistant',
        'content': response['content'],
        'citations': response.get('citations', []),
        'steps': response.get('steps', []),
        'proposal_id': response.get('proposal_id'),
        'used_kb': response.get('used_kb', False),
        'background_file_ids': active_background_file_ids,
        'created_at': now
    }
    chat['messages'].append(ai_message)

    # ???????????
    if response.get('proposal'):
        proposal_id = response['proposal_id']
        chat['proposals'][proposal_id] = response['proposal']

    chat['updated_at'] = now
    projects[project_id]['updated_at'] = now
    project_service.save_projects(projects)

    return ai_message


def send_message_stream(project_id, chat_id, content, use_web=False, background_file_ids=None):
    """
    发送消息并以流式方式获取AI回复（SSE格式）
    
    返回生成器，产生格式：
    {'type': 'start'} - 开始生成
    {'type': 'delta', 'content': '...'} - 内容片段
    {'type': 'citations', 'citations': [...]} - 引用信息
    {'type': 'proposal', 'proposal': {...}} - 变更提案
    {'type': 'end', 'message': {...}} - 完成
    """
    projects = project_service.load_projects()
    if project_id not in projects:
        yield {'type': 'error', 'error': '项目不存在'}
        return
    
    chats = projects[project_id].get('chats', {})
    if chat_id not in chats:
        yield {'type': 'error', 'error': '会话不存在'}
        return
    
    chat = chats[chat_id]
    if background_file_ids is not None:
        chat['background_file_ids'] = _normalize_background_file_ids(background_file_ids)
    active_background_file_ids = chat.get('background_file_ids', [])
    now = datetime.now().isoformat()
    
    # 添加用户消息
    user_message = {
        'id': str(uuid.uuid4())[:8],
        'role': 'user',
        'content': content,
        'created_at': now
    }
    chat['messages'].append(user_message)
    
    yield {'type': 'start'}
    
    # 获取历史对话
    history = _get_recent_history(chat.get('messages', []))

    tool_response = agent_service.run_tool_call(project_id, content, history)
    if tool_response:
        yield {'type': 'delta', 'content': tool_response.get('content', '')}
        if tool_response.get('steps'):
            yield {'type': 'steps', 'steps': tool_response.get('steps')}
        ai_message = {
            'id': str(uuid.uuid4())[:8],
            'role': 'assistant',
            'content': tool_response.get('content', ''),
            'citations': tool_response.get('citations', []),
            'steps': tool_response.get('steps', []),
            'proposal_id': tool_response.get('proposal_id'),
            'used_kb': tool_response.get('used_kb', False),
            'background_file_ids': active_background_file_ids,
            'created_at': datetime.now().isoformat()
        }
        chat['messages'].append(ai_message)
        chat['background_file_ids'] = active_background_file_ids
        chat['updated_at'] = datetime.now().isoformat()
        projects[project_id]['updated_at'] = datetime.now().isoformat()
        project_service.save_projects(projects)
        yield {'type': 'end', 'message': ai_message}
        return

    
    # 使用改进的意图识别
    intent_result = analyze_intent_with_llm(content, history)
    intent = intent_result['intent']

    stream_file_data = None
    stream_file_matches = []
    stream_file_context = None
    stream_file_error = None

    stream_file_intents = [
        'READ_FILE',
        'GENERATE_SUMMARY',
        'GENERATE_OUTLINE',
        'GENERATE_FLASHCARDS',
        'GENERATE_QUIZ',
        'GENERATE_GLOSSARY'
    ]

    if intent in stream_file_intents:
        if intent_result.get('target_file'):
            stream_file_data = get_file_data_by_name_or_id(project_id, intent_result.get('target_file'))
        else:
            stream_file_data, stream_file_matches = match_file_from_content(project_id, content)

        if not stream_file_data and stream_file_matches and not has_kb_keywords(content):
            names = ', '.join([f.get('name') for f in stream_file_matches if f.get('name')])
            stream_file_error = f'找到多个可能的文件，请指定文件名：{names}'
        elif not stream_file_data and intent == 'READ_FILE' and not has_kb_keywords(content):
            stream_file_error = '请说明要读取的文件名。'
        elif not stream_file_data and intent != 'READ_FILE' and not has_kb_keywords(content):
            stream_file_error = '请指明要操作的文件名，或说明要查询知识库。'
        elif stream_file_data:
            intent_result['target_file'] = intent_result.get('target_file') or stream_file_data.get('name') or stream_file_data.get('id')
            if intent != 'READ_FILE' and not stream_file_data.get('content'):
                stream_file_error = '文件 "{}" 无法读取文本内容，请确认是可编辑的文本文件。'.format(stream_file_data.get('name'))
            else:
                stream_file_context = (stream_file_data.get('content') or '')[:3000]
    
    # 收集完整回复内容
    full_content = []
    citations = []
    proposal = None
    proposal_id = None
    used_kb = False
    
    try:
        # 处理 READ_FILE 意图（不支持流式）
        if stream_file_error:
            response = {
                'content': stream_file_error,
                'citations': [],
                'used_kb': False
            }
            yield {'type': 'delta', 'content': stream_file_error}
            full_content.append(stream_file_error)
            citations = response.get('citations', [])
            used_kb = response.get('used_kb', False)
        elif intent == 'READ_FILE' and intent_result.get('target_file'):
            response = generate_file_read_response(project_id, intent_result['target_file'], content)
            # 模拟流式输出
            content_text = response['content']
            # 按句子分割输出
            import re
            sentences = re.split(r'([。！？.!?\n]+)', content_text)
            buffer = ''
            for i, sent in enumerate(sentences):
                buffer += sent
                if len(buffer) > 10 or i == len(sentences) - 1:
                    yield {'type': 'delta', 'content': buffer}
                    full_content.append(buffer)
                    buffer = ''
            citations = response.get('citations', [])
            used_kb = response.get('used_kb', False)
        else:
            # 处理其他意图，使用LLM流式生成
            # 判断是否需要查询知识库
            kb_results = []
            background_context, background_citations, valid_background_ids = _build_background_context(
                project_id,
                active_background_file_ids,
            )
            active_background_file_ids = valid_background_ids
            if stream_file_context:
                kb_results = [{
                    'text': stream_file_context,
                    'source': stream_file_data.get('name') if stream_file_data else '',
                    'page': 1,
                    'score': 1.0
                }]
                citations = [{
                    'source': stream_file_data.get('name') if stream_file_data else '',
                    'page': 1,
                    'score': 1.0
                }]
                yield {'type': 'citations', 'citations': citations}
            elif intent_result.get('needs_kb') or intent == 'QUERY_KB':
                kb_results = kb_service.search_kb(project_id, content, top_k=5)
                if kb_results:
                    used_kb = True
                    citations = [{
                        'source': r['source'],
                        'page': r['page'],
                        'score': r['score']
                    } for r in kb_results[:3]]
                    yield {'type': 'citations', 'citations': citations}
            elif background_citations:
                citations = background_citations
                yield {'type': 'citations', 'citations': citations}
            
            # 构建上下文
            context = None
            context_parts = []
            if background_context:
                context_parts.append(background_context)

            if kb_results:
                kb_context_parts = []
                for i, r in enumerate(kb_results[:3], 1):
                    kb_context_parts.append(f"[来源: {r['source']} 第{r['page']}页]\n{r['text']}")
                context_parts.append('\n\n---\n\n'.join(kb_context_parts))

            if context_parts:
                context = '\n\n---\n\n'.join(context_parts)
            
            # 使用LLM流式生成回复
            system_prompt = """你是一个专业的学习助手。请根据用户的问题提供准确、有帮助的回答。
如果提供了参考资料，请基于资料回答并注明来源。回答要结构清晰，必要时使用 Markdown 格式。"""
            
            user_message_content = content
            if context:
                user_message_content = f"参考资料：\n{context}\n\n用户问题：{content}\n\n请基于参考资料回答问题，并注明来源。"
            
            messages = [
                {"role": "system", "content": system_prompt}
            ]
            
            # 添加历史对话
            if history:
                for msg in history[:-1]:  # 排除刚添加的用户消息
                    if msg.get('role') in ['user', 'assistant']:
                        messages.append({
                            "role": msg['role'],
                            "content": msg['content']
                        })
            
            messages.append({"role": "user", "content": user_message_content})
            
            # 调用LLM流式生成
            full_text = ""
            for delta in llm_service.call_llm_stream(messages, temperature=0.7, max_tokens=2000):
                if delta:
                    full_text += delta
                    yield {'type': 'delta', 'content': delta}
            
            full_content = [full_text]
        
        # 保存AI回复
        ai_message = {
            'id': str(uuid.uuid4())[:8],
            'role': 'assistant',
            'content': ''.join(full_content) if isinstance(full_content, list) else full_content,
            'citations': citations,
            'proposal_id': proposal_id,
            'used_kb': used_kb,
            'background_file_ids': active_background_file_ids,
            'created_at': datetime.now().isoformat()
        }
        chat['messages'].append(ai_message)
        chat['background_file_ids'] = active_background_file_ids
        
        if proposal:
            chat['proposals'][proposal_id] = proposal
        
        chat['updated_at'] = datetime.now().isoformat()
        projects[project_id]['updated_at'] = datetime.now().isoformat()
        project_service.save_projects(projects)
        
        yield {'type': 'end', 'message': ai_message}
        
    except Exception as e:
        print(f"流式生成出错: {e}")
        import traceback
        traceback.print_exc()
        yield {'type': 'error', 'error': str(e)}


def generate_file_read_response(project_id, filename, question):
    """生成读取文件内容的回复"""
    from app.services import file_service
    
    # 查找文件
    files = file_service.list_files(project_id)
    target_file = None
    for f in files:
        if f.get('name') == filename or f.get('id') == filename:
            target_file = f
            break
    
    if not target_file:
        return {
            'content': f'抱歉，找不到文件 "{filename}"。请检查文件名是否正确，或者先上传该文件。',
            'citations': [],
            'used_kb': False
        }
    
    # 获取文件内容
    file_data = file_service.get_file(project_id, target_file['id'])
    if not file_data:
        return {
            'content': f'无法读取文件 "{filename}" 的内容。',
            'citations': [],
            'used_kb': False
        }
    
    content = file_data.get('content', '')
    if not content:
        return {
            'content': f'文件 "{filename}" 是空的或者无法读取文本内容（如图片文件）。',
            'citations': [],
            'used_kb': False
        }
    
    # 根据问题生成回复
    file_content_preview = content[:3000]  # 限制长度
    
    prompt = f"""文件 "{filename}" 的内容如下：

```
{file_content_preview}
```

用户问题：{question}

请基于文件内容回答用户的问题。如果文件内容不足以回答，请说明。回答时简要总结文件内容并回答具体问题。"""

    answer = llm_service.call_llm([
        {"role": "system", "content": "你是一个专业的文件分析助手。请基于文件内容回答用户问题。"},
        {"role": "user", "content": prompt}
    ])
    
    return {
        'content': answer or f'文件 "{filename}" 的内容：\n\n```\n{content[:2000]}\n```',
        'citations': [{'source': filename, 'page': 1}],
        'used_kb': True
    }


def analyze_intent(content):
    """分析用户意图"""
    content_lower = content.lower()
    
    # 创建笔记
    if any(kw in content_lower for kw in ['创建', '新建', '写一篇', '帮我写']):
        return 'CREATE_NOTE'
    
    # 修改笔记
    if any(kw in content_lower for kw in ['修改', '改一下', '编辑', '更新']):
        return 'EDIT_NOTE'
    
    # 删除
    if any(kw in content_lower for kw in ['删除', '删掉']):
        return 'DELETE_NOTE'
    
    # 生成摘要
    if any(kw in content_lower for kw in ['总结', '摘要', '概括']):
        return 'GENERATE_SUMMARY'
    
    # 生成大纲
    if any(kw in content_lower for kw in ['大纲', '目录', '结构']):
        return 'GENERATE_OUTLINE'
    
    # 生成卡片
    if any(kw in content_lower for kw in ['卡片', '复习卡', 'flashcard']):
        return 'GENERATE_FLASHCARDS'
    
    # 生成练习题
    if any(kw in content_lower for kw in ['练习题', '题目', '测验']):
        return 'GENERATE_QUIZ'
    
    # 生成术语表
    if any(kw in content_lower for kw in ['术语', '名词解释', '概念']):
        return 'GENERATE_GLOSSARY'
    
    # 默认为问答（可能查询知识库）
    return 'QUERY'


def generate_response(project_id, chat, content, intent, use_web, intent_result=None, background_file_ids=None):
    """生成AI回复"""
    response = {
        'content': '',
        'citations': [],
        'proposal': None,
        'proposal_id': None,
        'used_kb': False
    }
    
    # 获取历史对话
    history = _get_recent_history(chat.get('messages', []))

    background_context, background_citations, valid_background_ids = _build_background_context(
        project_id,
        background_file_ids,
    )
    if background_file_ids is not None:
        chat['background_file_ids'] = valid_background_ids

    file_context = None
    file_citation = None
    target_file = intent_result.get('target_file') if intent_result else None
    file_data = None
    file_matches = []

    file_intents = [
        'READ_FILE',
        'GENERATE_SUMMARY',
        'GENERATE_OUTLINE',
        'GENERATE_FLASHCARDS',
        'GENERATE_QUIZ',
        'GENERATE_GLOSSARY'
    ]

    if intent in file_intents:
        if target_file:
            file_data = get_file_data_by_name_or_id(project_id, target_file)
        else:
            file_data, file_matches = match_file_from_content(project_id, content)

        if not file_data and file_matches and not has_kb_keywords(content):
            names = ', '.join([f.get('name') for f in file_matches if f.get('name')])
            response['content'] = f'找到多个可能的文件，请指定文件名：{names}'
            return response

        if intent == 'READ_FILE':
            if file_data:
                return generate_file_read_response(project_id, file_data.get('id') or file_data.get('name'), content)
            if not has_kb_keywords(content):
                response['content'] = '请说明要读取的文件名。'
                return response

        if intent != 'READ_FILE' and not file_data and not has_kb_keywords(content):
            response['content'] = '请指明要操作的文件名，或说明要查询知识库。'
            return response

        if file_data:
            if not file_data.get('content'):
                response['content'] = '文件 "{}" 无法读取文本内容，请确认是可编辑的文本文件。'.format(file_data.get('name'))
                return response
            file_context = file_data.get('content', '')
            file_citation = {
                'source': file_data.get('name'),
                'page': 1
            }

    kb_results = []
    needs_kb = intent_result.get('needs_kb', False) if intent_result else should_use_knowledge_base(content, history)
    if file_context:
        needs_kb = False
    
    if needs_kb or intent == 'QUERY_KB':
        kb_results = kb_service.search_kb(project_id, content, top_k=5)
        if kb_results:
            response['used_kb'] = True
            response['citations'] = [{
                'source': r['source'],
                'page': r['page'],
                'score': r['score']
            } for r in kb_results[:3]]
    
    # 构建上下文
    context_parts = []
    citations = list(response.get('citations', []))

    if file_context:
        context_parts.append(file_context)
        if file_citation:
            citations = [file_citation] + citations

    if background_context:
        context_parts.append(background_context)
        citations = background_citations + citations

    if kb_results:
        kb_context_parts = []
        for i, r in enumerate(kb_results[:3], 1):
            kb_context_parts.append(f"[来源: {r['source']} 第{r['page']}页]\n{r['text']}")
        context_parts.append('\n\n---\n\n'.join(kb_context_parts))

    context = '\n\n---\n\n'.join([p for p in context_parts if p]) if context_parts else None
    response['citations'] = citations
    
    if intent == 'CREATE_NOTE':
        # 使用 LLM 生成笔记
        note_content = llm_service.generate_note(
            title=content,
            content_hint="请根据用户需求生成详细的笔记内容"
        )
        
        proposal_id = str(uuid.uuid4())[:8]
        response['content'] = f'我已为您创建了笔记，请查看右侧的变更提案，确认后点击应用。'
        response['proposal_id'] = proposal_id
        response['proposal'] = {
            'id': proposal_id,
            'type': 'create',
            'file_name': f'note_{datetime.now().strftime("%Y%m%d_%H%M%S")}.md',
            'summary': f'创建笔记：{content[:20]}...',
            'diff': {
                'old': '',
                'new': note_content or f'# {content}\n\n（内容生成失败，请重试）'
            },
            'status': 'pending'
        }
    
    elif intent == 'EDIT_NOTE':
        # 获取原文件内容（简化处理）
        original_content = "# 原笔记内容\n\n这是原来的内容..."
        
        # 使用 LLM 编辑笔记
        edited_content = llm_service.edit_note(original_content, content)
        
        proposal_id = str(uuid.uuid4())[:8]
        response['content'] = '我已修改笔记，请查看变更提案并确认。'
        response['proposal_id'] = proposal_id
        response['proposal'] = {
            'id': proposal_id,
            'type': 'edit',
            'file_name': 'note.md',
            'summary': '修改笔记内容',
            'diff': {
                'old': original_content,
                'new': edited_content or original_content
            },
            'status': 'pending'
        }
    
    elif intent == 'GENERATE_SUMMARY':
        # 如果有知识库内容，基于知识库生成摘要
        summary_content = llm_service.generate_summary(context if context else content)
        
        proposal_id = str(uuid.uuid4())[:8]
        response['content'] = '我已为您生成摘要，请查看变更提案。'
        response['proposal_id'] = proposal_id
        response['proposal'] = {
            'id': proposal_id,
            'type': 'create',
            'file_name': f'summary_{datetime.now().strftime("%Y%m%d")}.md',
            'summary': '生成学习摘要',
            'diff': {
                'old': '',
                'new': summary_content or '# 摘要\n\n（摘要生成失败，请重试）'
            },
            'status': 'pending'
        }
    
    elif intent == 'GENERATE_OUTLINE':
        # 使用 LLM 生成大纲
        outline_content = llm_service.generate_outline(context if context else content)
        
        proposal_id = str(uuid.uuid4())[:8]
        response['content'] = '我已为您生成学习大纲，请查看变更提案。'
        response['proposal_id'] = proposal_id
        response['proposal'] = {
            'id': proposal_id,
            'type': 'create',
            'file_name': f'outline_{datetime.now().strftime("%Y%m%d")}.md',
            'summary': '生成学习大纲',
            'diff': {
                'old': '',
                'new': outline_content or '# 大纲\n\n（大纲生成失败，请重试）'
            },
            'status': 'pending'
        }
    
    elif intent == 'GENERATE_FLASHCARDS':
        # 使用 LLM 生成学习卡片
        cards = llm_service.generate_flashcards(context if context else content)
        
        proposal_id = str(uuid.uuid4())[:8]
        response['content'] = '我已为您生成学习卡片，请查看变更提案。'
        response['proposal_id'] = proposal_id
        response['proposal'] = {
            'id': proposal_id,
            'type': 'create',
            'file_name': f'cards_{datetime.now().strftime("%Y%m%d")}.json',
            'summary': '生成学习卡片',
            'diff': {
                'old': '',
                'new': json.dumps(cards, ensure_ascii=False, indent=2) if cards else '[]'
            },
            'status': 'pending'
        }
    
    elif intent == 'GENERATE_QUIZ':
        # 使用 LLM 生成练习题
        quiz_content = llm_service.generate_quiz(context if context else content)
        
        proposal_id = str(uuid.uuid4())[:8]
        response['content'] = '我已为您生成练习题，请查看变更提案。'
        response['proposal_id'] = proposal_id
        response['proposal'] = {
            'id': proposal_id,
            'type': 'create',
            'file_name': f'quiz_{datetime.now().strftime("%Y%m%d")}.md',
            'summary': '生成练习题',
            'diff': {
                'old': '',
                'new': quiz_content or '# 练习题\n\n（题目生成失败，请重试）'
            },
            'status': 'pending'
        }
    
    elif intent == 'GENERATE_GLOSSARY':
        # 使用 LLM 生成术语表
        glossary_content = llm_service.generate_glossary(context if context else content)
        
        proposal_id = str(uuid.uuid4())[:8]
        response['content'] = '我已为您生成术语表，请查看变更提案。'
        response['proposal_id'] = proposal_id
        response['proposal'] = {
            'id': proposal_id,
            'type': 'create',
            'file_name': f'glossary_{datetime.now().strftime("%Y%m%d")}.md',
            'summary': '生成术语表',
            'diff': {
                'old': '',
                'new': glossary_content or '# 术语表\n\n（术语表生成失败，请重试）'
            },
            'status': 'pending'
        }
    
    else:
        # 普通问答 - 使用 LLM
        # 如果有知识库上下文，使用带上下文的回答
        if context:
            answer = llm_service.answer_with_context(
                question=content,
                context=context,
                history=history
            )
            response['content'] = answer or '抱歉，我暂时无法回答这个问题，请稍后重试。'
        else:
            # 没有知识库上下文，使用普通问答
            answer = llm_service.answer_question(content, None, history)
            response['content'] = answer or '抱歉，我暂时无法回答这个问题，请稍后重试。'
    
    return response


def apply_proposal(project_id, chat_id, proposal_id):
    """应用变更提案"""
    projects = project_service.load_projects()
    if project_id not in projects:
        return None
    
    chats = projects[project_id].get('chats', {})
    if chat_id not in chats:
        return None
    
    chat = chats[chat_id]
    proposals = chat.get('proposals', {})
    if proposal_id not in proposals:
        return None
    
    proposal = proposals[proposal_id]
    
    # 创建或更新文件
    if proposal['type'] == 'create':
        # 创建新文件
        file_name = proposal['file_name']
        content = proposal['diff']['new']
        
        # 这里简化处理，实际需要创建文件
        now = datetime.now().isoformat()
        file_id = str(uuid.uuid4())[:8]
        
        if 'files' not in projects[project_id]:
            projects[project_id]['files'] = {}
        
        projects[project_id]['files'][file_id] = {
            'id': file_id,
            'name': file_name,
            'type': 'text',
            'content': content,
            'created_at': now,
            'updated_at': now,
            'versions': [{
                'id': 'v1',
                'content': content,
                'created_at': now,
                'summary': proposal['summary']
            }]
        }
        
        result = {
            'file_id': file_id,
            'file_name': file_name,
            'action': 'created'
        }
    
    elif proposal['type'] == 'edit':
        # 更新现有文件
        result = {
            'file_name': proposal['file_name'],
            'action': 'updated'
        }
    
    # 标记提案已应用
    proposal['status'] = 'applied'
    
    projects[project_id]['updated_at'] = datetime.now().isoformat()
    project_service.save_projects(projects)
    
    return result


def reject_proposal(project_id, chat_id, proposal_id):
    """拒绝变更提案"""
    projects = project_service.load_projects()
    if project_id not in projects:
        return False
    
    chats = projects[project_id].get('chats', {})
    if chat_id not in chats:
        return False
    
    chat = chats[chat_id]
    proposals = chat.get('proposals', {})
    if proposal_id not in proposals:
        return False
    
    proposals[proposal_id]['status'] = 'rejected'
    project_service.save_projects(projects)
    
    return True


def generate_artifact(project_id, artifact_type, source, options):
    """生成学习成果"""
    projects = project_service.load_projects()
    if project_id not in projects:
        return None
    
    now = datetime.now().isoformat()
    artifact_id = str(uuid.uuid4())[:8]
    
    # 根据类型生成不同内容
    if artifact_type == 'summary':
        content = f'# 学习摘要\n\n## 概述\n这是自动生成的摘要内容。\n\n## 关键点\n- 要点1\n- 要点2\n'
        file_name = f'summary_{datetime.now().strftime("%Y%m%d")}.md'
    
    elif artifact_type == 'outline':
        content = '# 大纲\n\n## 第一章\n- 第一节\n- 第二节\n\n## 第二章\n- 第一节\n- 第二节\n'
        file_name = f'outline_{datetime.now().strftime("%Y%m%d")}.md'
    
    elif artifact_type == 'flashcards':
        content = json.dumps([
            {'question': '问题1', 'answer': '答案1'},
            {'question': '问题2', 'answer': '答案2'}
        ], ensure_ascii=False, indent=2)
        file_name = f'cards_{datetime.now().strftime("%Y%m%d")}.json'
    
    elif artifact_type == 'quiz':
        content = '# 练习题\n\n## 选择题\n1. 问题1\n   A. 选项A\n   B. 选项B\n   答案：A\n'
        file_name = f'quiz_{datetime.now().strftime("%Y%m%d")}.md'
    
    elif artifact_type == 'glossary':
        content = '# 术语表\n\n| 术语 | 解释 |\n|------|------|\n| 术语1 | 解释1 |\n| 术语2 | 解释2 |\n'
        file_name = f'glossary_{datetime.now().strftime("%Y%m%d")}.md'
    
    else:
        return None
    
    # 创建文件记录
    if 'files' not in projects[project_id]:
        projects[project_id]['files'] = {}
    
    projects[project_id]['files'][artifact_id] = {
        'id': artifact_id,
        'name': file_name,
        'type': 'text',
        'content': content,
        'created_at': now,
        'updated_at': now,
        'versions': [{
            'id': 'v1',
            'content': content,
            'created_at': now,
            'summary': f'自动生成{artifact_type}'
        }]
    }
    
    projects[project_id]['updated_at'] = now
    project_service.save_projects(projects)
    
    return {
        'id': artifact_id,
        'name': file_name,
        'type': artifact_type,
        'content': content
    }
