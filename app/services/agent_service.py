import json
from typing import Dict, Any, Optional, List, TypedDict
from langgraph.graph import StateGraph, END
from app.services import file_service, kb_service, llm_service

TOOLS_SPEC = [
    {
        "name": "list_files",
        "description": "List normal files uploaded in the project.",
        "args": {}
    },
    {
        "name": "read_file",
        "description": "Read a normal text file by name or id.",
        "args": {"name_or_id": "string"}
    },
    {
        "name": "update_file",
        "description": "Update a normal text file by id with new content.",
        "args": {"file_id": "string", "content": "string"}
    },
    {
        "name": "delete_file",
        "description": "Delete a normal file by id.",
        "args": {"file_id": "string"}
    },
    {
        "name": "list_kb_files",
        "description": "List knowledge base PDF files in the project.",
        "args": {}
    },
    {
        "name": "search_kb",
        "description": "Search the knowledge base PDFs by query.",
        "args": {"query": "string", "top_k": "int (optional)"}
    },
    {
        "name": "web_search",
        "description": "Stub for web search. Returns a placeholder response.",
        "args": {"query": "string"}
    }
]

SUMMARY_KEYWORDS = ["summary", "summarize"]
OUTLINE_KEYWORDS = ["outline"]
FLASHCARD_KEYWORDS = ["flashcard"]
QUIZ_KEYWORDS = ["quiz"]
GLOSSARY_KEYWORDS = ["glossary"]


class AgentState(TypedDict, total=False):
    query: str
    project_id: str
    decision: Dict[str, Any]
    tool_result: Dict[str, Any]
    final: Dict[str, Any]

def _summarize_result(text: str, limit: int = 160) -> str:
    if not text:
        return ""
    text = text.replace("\n", " ").strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "..."

def _with_steps(response: Dict[str, Any], tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    steps = [{
        "type": "tool_call",
        "tool": tool_name,
        "args": tool_args,
        "result": _summarize_result(response.get("content", ""))
    }]
    response["steps"] = steps
    return response


def _clean_json(text: str) -> str:
    if not text:
        return ""
    text = text.strip()
    if text.startswith('```'):
        text = text.split("\\n", 1)[1] if "\\n" in text else ""
        text = text.rsplit("\\n", 1)[0] if "\\n" in text else text
        text = text.replace('```json', '').replace('```', '').strip()
    return text


def decide_tool(query: str) -> Optional[Dict[str, Any]]:
    system_prompt = (
        "You are a tool selector. Choose an appropriate tool for the user query, "
        "or respond directly.\\n\\n"
        "Available tools:\\n" + json.dumps(TOOLS_SPEC, ensure_ascii=False) + "\\n\\n"
        "Return JSON only, no Markdown.\\n"
        "Format: {\\\"action\\\": \\\"tool\\\"|\\\"final\\\", \\\"tool_name\\\": \\\"...\\\", "
        "\\\"tool_args\\\": {...}, \\\"response\\\": \\\"...\\\"}"
    )
    user_prompt = f"User query: {query}"

    result = llm_service.call_llm([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ], temperature=0.1, max_tokens=500)

    if not result:
        return None

    try:
        parsed = json.loads(_clean_json(result))
        return parsed
    except Exception:
        return None


def _find_file_by_name_or_id(project_id: str, name_or_id: str) -> Optional[Dict[str, Any]]:
    files = file_service.list_files(project_id)
    for f in files:
        if f.get('id') == name_or_id or f.get('name') == name_or_id:
            return file_service.get_file(project_id, f.get('id'))
    return None


def _summarize_text(text: str) -> str:
    return llm_service.generate_summary(text)


def _outline_text(text: str) -> str:
    return llm_service.generate_outline(text)


def _flashcards_text(text: str) -> str:
    cards = llm_service.generate_flashcards(text)
    return json.dumps(cards, ensure_ascii=False, indent=2) if cards else "[]"


def _quiz_text(text: str) -> str:
    return llm_service.generate_quiz(text)


def _glossary_text(text: str) -> str:
    return llm_service.generate_glossary(text)


def _handle_read_or_transform(query: str, file_data: Dict[str, Any]) -> Dict[str, Any]:
    content = file_data.get('content') or ''
    if not content:
        return {
            'content': f'File "{file_data.get("name")}" has no readable text content.',
            'citations': [],
            'used_kb': False
        }

    lower = query.lower()
    if any(k in lower for k in SUMMARY_KEYWORDS):
        answer = _summarize_text(content)
    elif any(k in lower for k in OUTLINE_KEYWORDS):
        answer = _outline_text(content)
    elif any(k in lower for k in FLASHCARD_KEYWORDS):
        answer = _flashcards_text(content)
    elif any(k in lower for k in QUIZ_KEYWORDS):
        answer = _quiz_text(content)
    elif any(k in lower for k in GLOSSARY_KEYWORDS):
        answer = _glossary_text(content)
    else:
        preview = content[:3000]
        prompt = (
            f"File \"{file_data.get('name')}\" content:\\n\\n"
            f"```\\n{preview}\\n```\\n\\n"
            f"User query: {query}\\n\\n"
            "Answer based on the file content."
        )
        answer = llm_service.call_llm([
            {"role": "system", "content": "You are a file analysis assistant."},
            {"role": "user", "content": prompt}
        ])

    return {
        'content': answer or 'Sorry, I cannot generate a response right now.',
        'citations': [{'source': file_data.get('name'), 'page': 1}],
        'used_kb': False
    }


def _tool_execute(project_id: str, query: str, decision: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    tool_name = decision.get('tool_name')
    tool_args = decision.get('tool_args') or {}

    if tool_name == 'list_files':
        files = file_service.list_files(project_id)
        if not files:
            return _with_steps({
                'content': 'No normal files uploaded in this project yet.',
                'citations': [],
                'used_kb': False
            }, tool_name, tool_args)
        names = [f.get('name') for f in files if f.get('name')]
        file_lines = "\\n".join([f'- {name}' for name in names])
        return _with_steps({
            'content': f"Uploaded files:\\n{file_lines}",
            'citations': [],
            'used_kb': False
        }, tool_name, tool_args)

    if tool_name == 'read_file':
        name_or_id = tool_args.get('name_or_id')
        if not name_or_id:
            return _with_steps({
                'content': 'Please provide a file name or id to read.',
                'citations': [],
                'used_kb': False
            }, tool_name, tool_args)
        file_data = _find_file_by_name_or_id(project_id, name_or_id)
        if not file_data:
            return _with_steps({
                'content': f'File "{name_or_id}" was not found.',
                'citations': [],
                'used_kb': False
            }, tool_name, tool_args)
        return _handle_read_or_transform(query, file_data)

    if tool_name == 'update_file':
        file_id = tool_args.get('file_id')
        content = tool_args.get('content', '')
        if not file_id:
            return _with_steps({
                'content': 'Please provide a file id to update.',
                'citations': [],
                'used_kb': False
            }, tool_name, tool_args)
        result = file_service.update_file(project_id, file_id, content)
        if not result:
            return _with_steps({
                'content': 'File update failed. Check the file id.',
                'citations': [],
                'used_kb': False
            }, tool_name, tool_args)
        return _with_steps({
            'content': f'File "{result.get("name")}" updated.',
            'citations': [],
            'used_kb': False
        }, tool_name, tool_args)

    if tool_name == 'delete_file':
        file_id = tool_args.get('file_id')
        if not file_id:
            return _with_steps({
                'content': 'Please provide a file id to delete.',
                'citations': [],
                'used_kb': False
            }, tool_name, tool_args)
        success, error = file_service.delete_file(project_id, file_id, delete_kb_doc=False)
        if not success:
            return _with_steps({
                'content': error or 'Delete failed.',
                'citations': [],
                'used_kb': False
            }, tool_name, tool_args)
        return _with_steps({
            'content': 'File deleted.',
            'citations': [],
            'used_kb': False
        }, tool_name, tool_args)

    if tool_name == 'list_kb_files':
        files = file_service.list_kb_files(project_id)
        if not files:
            return _with_steps({
                'content': 'No knowledge base PDFs uploaded in this project yet.',
                'citations': [],
                'used_kb': False
            }, tool_name, tool_args)
        names = [f.get('name') for f in files if f.get('name')]
        file_lines = "\n".join([f'- {name}' for name in names])
        return _with_steps({
            'content': f"Knowledge base PDFs:\n{file_lines}",
            'citations': [],
            'used_kb': False
        }, tool_name, tool_args)

    if tool_name == 'search_kb':
        query_text = tool_args.get('query') or query
        top_k = tool_args.get('top_k', 5)
        results = kb_service.search_kb(project_id, query_text, top_k)
        if not results:
            return _with_steps({
                'content': 'No relevant knowledge base content was found.',
                'citations': [],
                'used_kb': False
            }, tool_name, tool_args)
        context_parts = []
        for r in results[:3]:
            context_parts.append(f"[Source: {r['source']} page {r['page']}]\\n{r['text']}")
        context = "\\n\\n---\\n\\n".join(context_parts)
        answer = llm_service.answer_with_context(query, context, None)
        citations = [{'source': r['source'], 'page': r['page'], 'score': r['score']} for r in results[:3]]
        return _with_steps({
            'content': answer or 'Sorry, I cannot generate a response right now.',
            'citations': citations,
            'used_kb': True
        }, tool_name, tool_args)

    if tool_name == 'web_search':
        query_text = tool_args.get('query') or query
        return _with_steps({
            'content': f'[stub] Web search not implemented yet. Query: {query_text}',
            'citations': [],
            'used_kb': False
        }, tool_name, tool_args)

    return None


def _decide_node(state: AgentState) -> AgentState:
    decision = decide_tool(state['query'])
    if decision:
        state['decision'] = decision
    return state


def _route(state: AgentState) -> str:
    decision = state.get('decision') or {}
    if decision.get('action') == 'tool':
        return 'tool'
    return END


def _tool_node(state: AgentState) -> AgentState:
    decision = state.get('decision') or {}
    result = _tool_execute(state['project_id'], state['query'], decision)
    if result:
        state['tool_result'] = result
    return state


def _respond_node(state: AgentState) -> AgentState:
    result = state.get('tool_result')
    if result:
        state['final'] = result
    return state


_graph = None

def _get_graph():
    global _graph
    if _graph is not None:
        return _graph
    builder = StateGraph(AgentState)
    builder.add_node('decide', _decide_node)
    builder.add_node('tool', _tool_node)
    builder.add_node('respond', _respond_node)
    builder.set_entry_point('decide')
    builder.add_conditional_edges('decide', _route, {'tool': 'tool', END: END})
    builder.add_edge('tool', 'respond')
    builder.add_edge('respond', END)
    _graph = builder.compile()
    return _graph


def run_tool_call(project_id: str, query: str) -> Optional[Dict[str, Any]]:
    graph = _get_graph()
    result = graph.invoke({'project_id': project_id, 'query': query})
    return result.get('final') if isinstance(result, dict) else None
