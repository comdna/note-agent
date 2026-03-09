import json
import os
import uuid
import shutil
from datetime import datetime
from werkzeug.utils import secure_filename
from app.services import project_service

DATA_DIR = None
UPLOAD_DIR = None

# 知识库PDF存储目录
KB_UPLOAD_DIR = None

def init_data_dir(data_dir, upload_dir):
    global DATA_DIR, UPLOAD_DIR, KB_UPLOAD_DIR
    DATA_DIR = data_dir
    UPLOAD_DIR = upload_dir
    # 知识库PDF单独存放
    KB_UPLOAD_DIR = os.path.join(upload_dir, 'knowledge_base')
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(KB_UPLOAD_DIR, exist_ok=True)

# 普通文件支持的类型
ALLOWED_EXTENSIONS = {
    'txt', 'md', 'json', 'py', 'js', 'html', 'css',
    'jpg', 'jpeg', 'png', 'gif', 'pdf'
}

# 知识库只允许PDF
KB_ALLOWED_EXTENSIONS = {'pdf'}

def allowed_file(filename, for_kb=False):
    """检查文件类型是否允许
    
    Args:
        filename: 文件名
        for_kb: 是否为知识库上传（只允许PDF）
    """
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    if for_kb:
        return ext in KB_ALLOWED_EXTENSIONS
    return ext in ALLOWED_EXTENSIONS


def _ensure_unique_filename(directory, filename):
    """Generate a non-conflicting filename in directory"""
    base, ext = os.path.splitext(filename)
    candidate = filename
    counter = 1
    while os.path.exists(os.path.join(directory, candidate)):
        candidate = f"{base}_{counter}{ext}"
        counter += 1
    return candidate

def get_file_type(filename):
    """获取文件类型"""
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    if ext == 'pdf':
        return 'pdf'
    elif ext in ['jpg', 'jpeg', 'png', 'gif']:
        return 'image'
    elif ext in ['txt', 'md', 'json', 'py', 'js', 'html', 'css']:
        return 'text'
    return 'document'

def list_files(project_id):
    """获取项目普通文件列表（不包含知识库PDF）"""
    projects = project_service.load_projects()
    if project_id not in projects:
        return []
    
    files = projects[project_id].get('files', {})
    result = []
    for fid, f in files.items():
        # 跳过知识库文件（通过metadata标记）
        if f.get('is_kb_file'):
            continue
        result.append({
            'id': fid,
            'name': f.get('name'),
            'type': f.get('type'),
            'size': f.get('size'),
            'created_at': f.get('created_at'),
            'updated_at': f.get('updated_at')
        })
    return sorted(result, key=lambda x: x['updated_at'], reverse=True)

def list_kb_files(project_id):
    """获取项目知识库PDF文件列表"""
    projects = project_service.load_projects()
    if project_id not in projects:
        return []
    
    files = projects[project_id].get('files', {})
    result = []
    for fid, f in files.items():
        # 只返回知识库文件
        if not f.get('is_kb_file'):
            continue
        result.append({
            'id': fid,
            'name': f.get('name'),
            'type': f.get('type'),
            'size': f.get('size'),
            'doc_id': f.get('doc_id'),  # 关联的知识库文档ID
            'page_count': f.get('page_count', 0),
            'created_at': f.get('created_at'),
            'updated_at': f.get('updated_at')
        })
    return sorted(result, key=lambda x: x['updated_at'], reverse=True)

def save_file(project_id, file, file_type=None, for_kb=False):
    """保存上传的文件
    
    Args:
        project_id: 项目ID
        file: 文件对象
        file_type: 指定的文件类型（可选）
        for_kb: 是否为知识库文件（PDF）
    """
    if not file or file.filename == '':
        return None
    
    filename = secure_filename(file.filename)
    if not allowed_file(filename, for_kb=for_kb):
        return None
    
    # 确定文件类型
    detected_type = get_file_type(filename)
    actual_type = file_type or detected_type
    
    # 知识库文件强制类型为pdf
    if for_kb and actual_type != 'pdf':
        return None
    
    # 生成文件ID和存储路径
    file_id = str(uuid.uuid4())[:8]
    
    if for_kb:
        # 知识库文件存放到专用目录
        project_kb_dir = os.path.join(KB_UPLOAD_DIR, project_id)
        os.makedirs(project_kb_dir, exist_ok=True)
        stored_name = _ensure_unique_filename(project_kb_dir, filename)
        file_path = os.path.join(project_kb_dir, stored_name)
        filename = stored_name
    else:
        # 普通文件存放到普通目录
        project_upload_dir = os.path.join(UPLOAD_DIR, project_id)
        os.makedirs(project_upload_dir, exist_ok=True)
        stored_name = _ensure_unique_filename(project_upload_dir, filename)
        file_path = os.path.join(project_upload_dir, stored_name)
        filename = stored_name
    
    # 保存文件
    file.save(file_path)
    
    # 读取文本文件内容
    content = None
    if actual_type == 'text' and not for_kb:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except:
            content = ""
    
    # 获取文件大小
    file_size = os.path.getsize(file_path)
    
    # 更新项目数据
    projects = project_service.load_projects()
    now = datetime.now().isoformat()
    
    file_data = {
        'id': file_id,
        'name': filename,
        'type': actual_type,
        'size': file_size,
        'path': file_path,
        'content': content,
        'is_kb_file': for_kb,  # 标记是否为知识库文件
        'created_at': now,
        'updated_at': now,
    }
    
    # 普通文件才有版本管理
    if not for_kb:
        file_data['versions'] = [{
            'id': 'v1',
            'content': content,
            'created_at': now,
            'summary': '初始版本'
        }]
    
    if project_id in projects:
        if 'files' not in projects[project_id]:
            projects[project_id]['files'] = {}
        projects[project_id]['files'][file_id] = file_data
        projects[project_id]['updated_at'] = now
        project_service.save_projects(projects)
    
    result = {
        'id': file_id,
        'name': filename,
        'type': actual_type,
        'size': file_size,
        'created_at': now,
        'updated_at': now
    }
    
    if for_kb:
        result['is_kb_file'] = True
    
    return result

def get_file(project_id, file_id):
    """获取文件详情"""
    projects = project_service.load_projects()
    if project_id not in projects:
        return None
    
    files = projects[project_id].get('files', {})
    if file_id not in files:
        return None
    
    f = files[file_id]
    result = {
        'id': file_id,
        'name': f.get('name'),
        'type': f.get('type'),
        'size': f.get('size'),
        'path': f.get('path'),  # 包含文件路径
        'content': f.get('content'),
        'is_kb_file': f.get('is_kb_file', False),
        'created_at': f.get('created_at'),
        'updated_at': f.get('updated_at')
    }
    
    # 知识库文件额外信息
    if f.get('is_kb_file'):
        result['doc_id'] = f.get('doc_id')
        result['page_count'] = f.get('page_count', 0)
    
    return result

def update_file(project_id, file_id, content):
    """更新文件内容（仅普通文件）"""
    projects = project_service.load_projects()
    if project_id not in projects:
        return None
    
    files = projects[project_id].get('files', {})
    if file_id not in files:
        return None
    
    f = files[file_id]
    
    # 知识库文件不允许编辑
    if f.get('is_kb_file'):
        return None
    
    now = datetime.now().isoformat()
    
    # 创建新版本
    version_id = f"v{len(f.get('versions', [])) + 1}"
    new_version = {
        'id': version_id,
        'content': content,
        'created_at': now,
        'summary': '用户编辑'
    }
    
    if 'versions' not in f:
        f['versions'] = []
    f['versions'].append(new_version)
    
    # 更新文件
    f['content'] = content
    f['updated_at'] = now
    
    # 如果是文本文件，同步更新磁盘文件
    if f.get('type') == 'text' and f.get('path'):
        try:
            with open(f['path'], 'w', encoding='utf-8') as file:
                file.write(content)
        except:
            pass
    
    projects[project_id]['updated_at'] = now
    project_service.save_projects(projects)
    
    return {
        'id': file_id,
        'name': f.get('name'),
        'type': f.get('type'),
        'content': content,
        'updated_at': now,
        'version': version_id
    }

def delete_file(project_id, file_id, delete_kb_doc=True):
    """删除文件
    
    Args:
        project_id: 项目ID
        file_id: 文件ID
        delete_kb_doc: 是否同时删除知识库文档（默认True）
    """
    projects = project_service.load_projects()
    if project_id not in projects:
        return False, '项目不存在'
    
    files = projects[project_id].get('files', {})
    if file_id not in files:
        return False, '文件不存在'
    
    f = files[file_id]
    is_kb_file = f.get('is_kb_file', False)
    
    # 如果是知识库文件，同时删除知识库文档
    if is_kb_file and delete_kb_doc:
        from app.services import kb_service
        doc_id = f.get('doc_id')
        if doc_id:
            kb_service.remove_pdf_from_kb(project_id, doc_id)
    
    # 删除磁盘文件
    if f.get('path') and os.path.exists(f['path']):
        os.remove(f['path'])
    
    del files[file_id]
    projects[project_id]['updated_at'] = datetime.now().isoformat()
    project_service.save_projects(projects)
    
    return True, None

def update_kb_file_doc_id(project_id, file_id, doc_id, page_count=0):
    """更新知识库文件的doc_id（添加到知识库后调用）"""
    projects = project_service.load_projects()
    if project_id not in projects:
        return False
    
    files = projects[project_id].get('files', {})
    if file_id not in files:
        return False
    
    f = files[file_id]
    if not f.get('is_kb_file'):
        return False
    
    f['doc_id'] = doc_id
    f['page_count'] = page_count
    f['updated_at'] = datetime.now().isoformat()
    
    project_service.save_projects(projects)
    return True

def get_versions(project_id, file_id):
    """获取文件版本历史（仅普通文件）"""
    projects = project_service.load_projects()
    if project_id not in projects:
        return []
    
    files = projects[project_id].get('files', {})
    if file_id not in files:
        return []
    
    f = files[file_id]
    # 知识库文件没有版本
    if f.get('is_kb_file'):
        return []
    
    versions = f.get('versions', [])
    return [{
        'id': v.get('id'),
        'created_at': v.get('created_at'),
        'summary': v.get('summary')
    } for v in reversed(versions)]

def rollback(project_id, file_id, version_id):
    """回滚到指定版本（仅普通文件）"""
    projects = project_service.load_projects()
    if project_id not in projects:
        return None
    
    files = projects[project_id].get('files', {})
    if file_id not in files:
        return None
    
    f = files[file_id]
    # 知识库文件不支持回滚
    if f.get('is_kb_file'):
        return None
    
    versions = f.get('versions', [])
    
    target_version = None
    for v in versions:
        if v['id'] == version_id:
            target_version = v
            break
    
    if not target_version:
        return None
    
    now = datetime.now().isoformat()
    
    # 创建回滚版本
    new_version_id = f"v{len(versions) + 1}"
    new_version = {
        'id': new_version_id,
        'content': target_version['content'],
        'created_at': now,
        'summary': f'回滚到 {version_id}'
    }
    versions.append(new_version)
    
    f['content'] = target_version['content']
    f['updated_at'] = now
    
    # 同步磁盘文件
    if f.get('type') == 'text' and f.get('path'):
        try:
            with open(f['path'], 'w', encoding='utf-8') as file:
                file.write(target_version['content'])
        except:
            pass
    
    projects[project_id]['updated_at'] = now
    project_service.save_projects(projects)
    
    return {
        'id': file_id,
        'name': f.get('name'),
        'content': f['content'],
        'updated_at': now,
        'version': new_version_id
    }
