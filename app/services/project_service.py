import json
import os
import uuid
from datetime import datetime

DATA_DIR = None

def init_data_dir(data_dir):
    global DATA_DIR
    DATA_DIR = data_dir
    os.makedirs(DATA_DIR, exist_ok=True)

def get_projects_file():
    return os.path.join(DATA_DIR, 'projects.json')

def load_projects():
    filepath = get_projects_file()
    if not os.path.exists(filepath):
        return {}
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_projects(projects):
    filepath = get_projects_file()
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(projects, f, ensure_ascii=False, indent=2)

def list_projects():
    """获取所有项目列表"""
    projects = load_projects()
    result = []
    for pid, p in projects.items():
        result.append({
            'id': pid,
            'name': p.get('name'),
            'description': p.get('description', ''),
            'created_at': p.get('created_at'),
            'updated_at': p.get('updated_at')
        })
    return sorted(result, key=lambda x: x['updated_at'], reverse=True)

def create_project(name, description=''):
    """创建新项目"""
    projects = load_projects()
    project_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()
    
    project = {
        'id': project_id,
        'name': name,
        'description': description,
        'created_at': now,
        'updated_at': now,
        'files': {},
        'kbs': {},
        'chats': {}
    }
    
    projects[project_id] = project
    save_projects(projects)
    
    return {
        'id': project_id,
        'name': name,
        'description': description,
        'created_at': now,
        'updated_at': now
    }

def get_project(project_id):
    """获取项目详情"""
    projects = load_projects()
    if project_id not in projects:
        return None
    
    p = projects[project_id]
    return {
        'id': project_id,
        'name': p.get('name'),
        'description': p.get('description', ''),
        'created_at': p.get('created_at'),
        'updated_at': p.get('updated_at'),
        'file_count': len(p.get('files', {})),
        'kb_count': len(p.get('kbs', {})),
        'chat_count': len(p.get('chats', {}))
    }

def delete_project(project_id):
    """删除项目"""
    projects = load_projects()
    if project_id not in projects:
        return False
    
    # 删除项目关联的知识库文件
    kb_dir = os.path.join(DATA_DIR, 'knowledge_bases', project_id)
    if os.path.exists(kb_dir):
        import shutil
        shutil.rmtree(kb_dir)
    
    # 删除项目关联的上传文件
    upload_dir = os.path.join(os.path.dirname(DATA_DIR), 'uploads', project_id)
    if os.path.exists(upload_dir):
        import shutil
        shutil.rmtree(upload_dir)
    
    del projects[project_id]
    save_projects(projects)
    return True

def update_project_timestamp(project_id):
    """更新项目时间戳"""
    projects = load_projects()
    if project_id in projects:
        projects[project_id]['updated_at'] = datetime.now().isoformat()
        save_projects(projects)
