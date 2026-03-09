from flask import Blueprint, request, jsonify, current_app
import json
from app.services import project_service, file_service, kb_service, chat_service
import os

bp = Blueprint('api', __name__)

# ==================== 项目管理 ====================

@bp.route('/projects', methods=['GET'])
def list_projects():
    """获取所有项目列表"""
    projects = project_service.list_projects()
    return jsonify({'projects': projects})

@bp.route('/projects', methods=['POST'])
def create_project():
    """创建新项目"""
    data = request.get_json()
    name = data.get('name', '').strip()
    description = data.get('description', '')
    
    if not name:
        return jsonify({'error': '项目名称不能为空'}), 400
    
    project = project_service.create_project(name, description)
    return jsonify({'project': project}), 201

@bp.route('/projects/<project_id>', methods=['GET'])
def get_project(project_id):
    """获取项目详情"""
    project = project_service.get_project(project_id)
    if not project:
        return jsonify({'error': '项目不存在'}), 404
    return jsonify({'project': project})

@bp.route('/projects/<project_id>', methods=['DELETE'])
def delete_project(project_id):
    """删除项目"""
    success = project_service.delete_project(project_id)
    if not success:
        return jsonify({'error': '项目不存在'}), 404
    return jsonify({'success': True})

# ==================== 普通文件管理（支持多种类型） ====================

@bp.route('/projects/<project_id>/files', methods=['GET'])
def list_files(project_id):
    """获取项目普通文件列表（txt, md, json, py, 图片等）"""
    files = file_service.list_files(project_id)
    return jsonify({'files': files})

@bp.route('/projects/<project_id>/files', methods=['POST'])
def upload_file(project_id):
    """上传普通文件（支持 txt, md, json, py, js, html, css, jpg, png, gif, pdf等）"""
    import traceback
    
    try:
        saved_files = []
        
        # 处理多文件上传（字段名 'files'）
        if 'files' in request.files:
            files = request.files.getlist('files')
            
            for file in files:
                if file.filename == '':
                    continue
                # for_kb=False 表示普通文件
                result = file_service.save_file(project_id, file, for_kb=False)
                if result:
                    saved_files.append(result)
        
        # 处理单文件上传（字段名 'file'，向后兼容）
        elif 'file' in request.files:
            file = request.files['file']
            if file.filename == '':
                return jsonify({'error': '没有选择文件'}), 400
            
            result = file_service.save_file(project_id, file, for_kb=False)
            if result:
                saved_files.append(result)
        
        else:
            return jsonify({'error': '没有上传文件'}), 400
        
        if not saved_files:
            return jsonify({'error': '文件保存失败，请检查文件类型是否支持'}), 400
        
        # 单文件返回 file，多文件返回 files 保持兼容
        if len(saved_files) == 1:
            return jsonify({'file': saved_files[0]}), 201
        return jsonify({'files': saved_files}), 201
        
    except Exception as e:
        current_app.logger.error(f"上传文件出错: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        return jsonify({'error': f'服务器错误: {str(e)}'}), 500

@bp.route('/projects/<project_id>/files/<file_id>', methods=['GET'])
def get_file(project_id, file_id):
    """获取文件内容"""
    file_data = file_service.get_file(project_id, file_id)
    if not file_data:
        return jsonify({'error': '文件不存在'}), 404
    # 知识库文件不能通过普通文件接口访问
    if file_data.get('is_kb_file'):
        return jsonify({'error': '请使用知识库接口访问此文件'}), 400
    return jsonify({'file': file_data})

@bp.route('/projects/<project_id>/files/<file_id>', methods=['PUT'])
def update_file(project_id, file_id):
    """更新文件内容（仅普通文件）"""
    data = request.get_json()
    content = data.get('content', '')
    
    result = file_service.update_file(project_id, file_id, content)
    if not result:
        return jsonify({'error': '文件更新失败，可能是知识库文件或不存在'}), 400
    return jsonify({'file': result})

@bp.route('/projects/<project_id>/files/<file_id>', methods=['DELETE'])
def delete_file(project_id, file_id):
    """删除普通文件"""
    success, error = file_service.delete_file(project_id, file_id, delete_kb_doc=False)
    if not success:
        return jsonify({'error': error or '文件不存在'}), 404
    return jsonify({'success': True})

@bp.route('/projects/<project_id>/files/<file_id>/versions', methods=['GET'])
def get_file_versions(project_id, file_id):
    """获取文件版本历史"""
    versions = file_service.get_versions(project_id, file_id)
    return jsonify({'versions': versions})

@bp.route('/projects/<project_id>/files/<file_id>/rollback/<version_id>', methods=['POST'])
def rollback_file(project_id, file_id, version_id):
    """回滚文件到指定版本"""
    result = file_service.rollback(project_id, file_id, version_id)
    if not result:
        return jsonify({'error': '回滚失败'}), 500
    return jsonify({'file': result})

# ==================== 知识库文件管理（只允许PDF） ====================

@bp.route('/projects/<project_id>/kb/files', methods=['GET'])
def list_kb_files(project_id):
    """获取知识库PDF文件列表"""
    files = file_service.list_kb_files(project_id)
    return jsonify({'files': files})

@bp.route('/projects/<project_id>/kb/files', methods=['POST'])
def upload_kb_file(project_id):
    """
    上传知识库PDF文件（只允许PDF）
    
    上传后文件会自动解析并添加到知识库索引
    """
    import traceback
    
    try:
        saved_files = []
        
        # 处理多文件上传（字段名 'files'）
        if 'files' in request.files:
            files = request.files.getlist('files')
            
            for file in files:
                if file.filename == '':
                    continue
                # for_kb=True 表示知识库文件
                result = file_service.save_file(project_id, file, for_kb=True)
                if result:
                    saved_files.append(result)
        
        # 处理单文件上传（字段名 'file'）
        elif 'file' in request.files:
            file = request.files['file']
            if file.filename == '':
                return jsonify({'error': '没有选择文件'}), 400
            
            result = file_service.save_file(project_id, file, for_kb=True)
            if result:
                saved_files.append(result)
        
        else:
            return jsonify({'error': '没有上传文件'}), 400
        
        if not saved_files:
            return jsonify({'error': '文件保存失败，请检查是否为有效的PDF文件'}), 400
        
        # 自动处理添加到知识库
        processed_files = []
        for file_info in saved_files:
            file_id = file_info['id']
            file_data = file_service.get_file(project_id, file_id)
            
            if file_data:
                # 自动添加到知识库索引
                kb_result = kb_service.add_pdf_to_kb(
                    project_id=project_id,
                    file_id=file_id,
                    file_path=file_data.get('path'),
                    file_name=file_data.get('name')
                )
                
                if kb_result:
                    file_info['kb_status'] = 'indexed'
                    file_info['doc_id'] = kb_result.get('doc_id')
                    file_info['page_count'] = kb_result.get('page_count')
                else:
                    file_info['kb_status'] = 'failed'
            
            processed_files.append(file_info)
        
        # 单文件返回 file，多文件返回 files 保持兼容
        if len(processed_files) == 1:
            return jsonify({'file': processed_files[0]}), 201
        return jsonify({'files': processed_files}), 201
        
    except Exception as e:
        current_app.logger.error(f"上传知识库文件出错: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        return jsonify({'error': f'服务器错误: {str(e)}'}), 500

@bp.route('/projects/<project_id>/kb/files/<file_id>', methods=['GET'])
def get_kb_file(project_id, file_id):
    """获取知识库文件详情"""
    file_data = file_service.get_file(project_id, file_id)
    if not file_data:
        return jsonify({'error': '文件不存在'}), 404
    if not file_data.get('is_kb_file'):
        return jsonify({'error': '这不是知识库文件'}), 400
    return jsonify({'file': file_data})

@bp.route('/projects/<project_id>/kb/files/<file_id>', methods=['DELETE'])
def delete_kb_file(project_id, file_id):
    """删除知识库PDF文件（同时删除向量索引）"""
    success, error = file_service.delete_file(project_id, file_id, delete_kb_doc=True)
    if not success:
        return jsonify({'error': error or '文件不存在'}), 404
    return jsonify({'success': True})

# ==================== 知识库管理（每个项目只有一个知识库） ====================

@bp.route('/projects/<project_id>/kb', methods=['GET'])
def get_kb(project_id):
    """获取项目知识库信息和统计"""
    kb = kb_service.get_kb(project_id)
    if not kb:
        return jsonify({'error': '知识库不存在'}), 404
    
    # 获取统计信息
    stats = kb_service.get_kb_stats(project_id)
    
    return jsonify({
        'kb': {
            'project_id': project_id,
            'stats': stats,
            'created_at': kb.get('created_at'),
            'updated_at': kb.get('updated_at')
        }
    })

@bp.route('/projects/<project_id>/kb/search', methods=['POST'])
def search_kb(project_id):
    """
    在知识库中搜索
    
    请求体：
    {
        "query": "搜索文本",
        "top_k": 5  # 可选，默认5
    }
    """
    data = request.get_json()
    query = data.get('query', '').strip()
    top_k = data.get('top_k', 5)
    
    if not query:
        return jsonify({'error': '搜索内容不能为空'}), 400
    
    results = kb_service.search_kb(project_id, query, top_k)
    return jsonify({'results': results})

# ==================== 聊天与问答 ====================

@bp.route('/projects/<project_id>/chats', methods=['GET'])
def list_chats(project_id):
    """获取项目会话列表"""
    chats = chat_service.list_chats(project_id)
    return jsonify({'chats': chats})

@bp.route('/projects/<project_id>/chats', methods=['POST'])
def create_chat(project_id):
    """创建新会话"""
    data = request.get_json()
    title = data.get('title', '新对话')
    
    chat = chat_service.create_chat(project_id, title)
    return jsonify({'chat': chat}), 201

@bp.route('/projects/<project_id>/chats/<chat_id>', methods=['GET'])
def get_chat(project_id, chat_id):
    """获取会话详情和消息"""
    chat = chat_service.get_chat(project_id, chat_id)
    if not chat:
        return jsonify({'error': '会话不存在'}), 404
    return jsonify({'chat': chat})


@bp.route('/projects/<project_id>/chats/<chat_id>', methods=['DELETE'])
def delete_chat(project_id, chat_id):
    """删除会话"""
    success = chat_service.delete_chat(project_id, chat_id)
    if not success:
        return jsonify({'error': '会话不存在或删除失败'}), 404
    return jsonify({'success': True})


@bp.route('/projects/<project_id>/chats/<chat_id>/messages', methods=['GET'])
def get_chat_messages(project_id, chat_id):
    """获取会话消息列表"""
    chat = chat_service.get_chat(project_id, chat_id)
    if not chat:
        return jsonify({'error': '会话不存在'}), 404
    return jsonify({'messages': chat.get('messages', [])})


@bp.route('/projects/<project_id>/chats/<chat_id>/background-files', methods=['PUT'])
def set_chat_background_files(project_id, chat_id):
    data = request.get_json() or {}
    file_ids = data.get('background_file_ids', [])
    result = chat_service.set_chat_background_files(project_id, chat_id, file_ids)
    if result is None:
        return jsonify({'error': '会话不存在或项目不存在'}), 404
    return jsonify(result)

@bp.route('/projects/<project_id>/chats/<chat_id>/messages', methods=['POST'])
def send_message_to_chat(project_id, chat_id):
    """
    发送消息到指定会话（非流式）
    
    系统会自动判断是否需要查询知识库
    """
    data = request.get_json()
    content = data.get('content', '').strip()
    use_web = data.get('use_web', False)
    background_file_ids = data.get('background_file_ids')
    
    if not content:
        return jsonify({'error': '消息内容不能为空'}), 400
    
    result = chat_service.send_message(project_id, chat_id, content, use_web, background_file_ids)
    if not result:
        return jsonify({'error': '发送消息失败'}), 500
    return jsonify({'message': result})


@bp.route('/projects/<project_id>/chats/<chat_id>/stream', methods=['POST'])
def send_message_stream(project_id, chat_id):
    """
    发送消息到指定会话（流式输出，SSE）
    
    使用 Server-Sent Events 格式返回流式响应
    """
    data = request.get_json()
    content = data.get('content', '').strip()
    use_web = data.get('use_web', False)
    background_file_ids = data.get('background_file_ids')
    
    if not content:
        return jsonify({'error': '消息内容不能为空'}), 400
    
    from flask import Response, stream_with_context
    
    def generate():
        for chunk in chat_service.send_message_stream(project_id, chat_id, content, use_web, background_file_ids):
            yield f"data: {json.dumps(chunk)}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )

@bp.route('/projects/<project_id>/chat', methods=['POST'])
def chat_simple(project_id):
    """简化聊天接口（自动创建或使用默认会话）"""
    data = request.get_json()
    content = data.get('message', data.get('content', '')).strip()
    use_web = data.get('web_search', data.get('use_web', False))
    background_file_ids = data.get('background_file_ids')
    
    if not content:
        return jsonify({'error': '消息内容不能为空'}), 400
    
    # 获取或创建会话
    chats = chat_service.list_chats(project_id)
    if chats:
        chat = chats[0]  # 使用第一个现有会话
        chat_id = chat['id']
    else:
        chat = chat_service.create_chat(project_id, '默认会话')
        chat_id = chat['id']
    
    result = chat_service.send_message(project_id, chat_id, content, use_web, background_file_ids)
    if not result:
        return jsonify({'error': '发送消息失败'}), 500
    
    return jsonify({
        'reply': result.get('content', ''),
        'message': result,
        'used_kb': result.get('used_kb', False)  # 返回是否使用了知识库
    })

@bp.route('/projects/<project_id>/chats/<chat_id>/proposals/<proposal_id>/apply', methods=['POST'])
def apply_proposal(project_id, chat_id, proposal_id):
    """应用变更提案"""
    result = chat_service.apply_proposal(project_id, chat_id, proposal_id)
    if not result:
        return jsonify({'error': '应用提案失败'}), 500
    return jsonify({'result': result})

@bp.route('/projects/<project_id>/chats/<chat_id>/proposals/<proposal_id>/reject', methods=['POST'])
def reject_proposal(project_id, chat_id, proposal_id):
    """拒绝变更提案"""
    success = chat_service.reject_proposal(project_id, chat_id, proposal_id)
    if not success:
        return jsonify({'error': '拒绝提案失败'}), 500
    return jsonify({'success': True})

# ==================== 学习成果生成 ====================

@bp.route('/projects/<project_id>/generate', methods=['POST'])
def generate_artifact(project_id):
    """生成学习成果"""
    data = request.get_json()
    artifact_type = data.get('type')  # summary, outline, flashcards, quiz, glossary
    source = data.get('source')  # file_id or kb_id
    options = data.get('options', {})
    
    if not artifact_type or not source:
        return jsonify({'error': '缺少必要参数'}), 400
    
    result = chat_service.generate_artifact(project_id, artifact_type, source, options)
    if not result:
        return jsonify({'error': '生成失败'}), 500
    return jsonify({'artifact': result})
