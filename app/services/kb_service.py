import os
import json
import uuid
import pickle
import numpy as np
from datetime import datetime
from typing import List, Dict, Optional
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
import faiss

from app.services import project_service

# 全局embedding模型（懒加载）
_embedding_model = None

def get_embedding_model():
    """获取embedding模型（懒加载）"""
    global _embedding_model
    if _embedding_model is None:
        # 使用轻量级的中文embedding模型
        _embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    return _embedding_model

# 数据目录
DATA_DIR = None
UPLOAD_DIR = None

def init_data_dir(data_dir, upload_dir):
    """初始化数据目录"""
    global DATA_DIR, UPLOAD_DIR
    DATA_DIR = data_dir
    UPLOAD_DIR = upload_dir
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)


def _get_kb_dir(project_id: str) -> str:
    """获取项目知识库目录"""
    kb_dir = os.path.join(DATA_DIR, 'knowledge_bases', project_id)
    os.makedirs(kb_dir, exist_ok=True)
    return kb_dir


def _get_faiss_path(kb_dir: str, doc_id: str) -> str:
    """获取FAISS索引文件路径"""
    return os.path.join(kb_dir, f"{doc_id}.faiss")


def _get_meta_path(kb_dir: str, doc_id: str) -> str:
    """获取元数据文件路径"""
    return os.path.join(kb_dir, f"{doc_id}.json")


def parse_pdf(file_path: str) -> List[Dict]:
    """
    解析PDF文件，返回每页的文本内容
    
    Returns:
        List[Dict]: 每页的内容，包含page_num和text
    """
    pages = []
    try:
        reader = PdfReader(file_path)
        for i, page in enumerate(reader.pages, 1):
            text = page.extract_text()
            if text and text.strip():
                pages.append({
                    'page_num': i,
                    'text': text.strip()
                })
    except Exception as e:
        print(f"PDF解析失败 {file_path}: {e}")
    return pages


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """
    将文本切分成chunks
    
    Args:
        text: 原文本
        chunk_size: 每个chunk的最大字符数
        overlap: 相邻chunk的重叠字符数
    
    Returns:
        List[str]: chunks列表
    """
    if not text or len(text) <= chunk_size:
        return [text] if text else []
    
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - overlap
    return chunks


def create_kb_for_project(project_id: str) -> Dict:
    """
    为项目创建知识库（每个项目只有一个知识库）
    """
    kb_dir = _get_kb_dir(project_id)
    
    # 创建知识库元数据
    kb_meta = {
        'project_id': project_id,
        'created_at': datetime.now().isoformat(),
        'updated_at': datetime.now().isoformat(),
        'documents': {}  # 存储文档信息
    }
    
    # 保存元数据
    meta_path = os.path.join(kb_dir, 'kb_meta.json')
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(kb_meta, f, ensure_ascii=False, indent=2)
    
    return kb_meta


def get_kb(project_id: str) -> Optional[Dict]:
    """
    获取项目知识库信息
    """
    kb_dir = _get_kb_dir(project_id)
    meta_path = os.path.join(kb_dir, 'kb_meta.json')
    
    if not os.path.exists(meta_path):
        # 自动创建知识库
        return create_kb_for_project(project_id)
    
    with open(meta_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def add_pdf_to_kb(project_id: str, file_id: str, file_path: str, file_name: str) -> Optional[Dict]:
    """
    将PDF文件添加到知识库（处理并创建向量索引）
    
    处理流程：
    1. 解析PDF文本
    2. 切分chunks
    3. 生成embeddings
    4. 创建FAISS索引
    5. 保存元数据
    6. 更新文件记录的doc_id关联
    """
    from app.services import file_service
    
    try:
        # 获取知识库
        kb = get_kb(project_id)
        kb_dir = _get_kb_dir(project_id)
        
        # 生成文档ID
        doc_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()
        
        # 1. 解析PDF
        pages = parse_pdf(file_path)
        if not pages:
            return None
        
        # 2. 切分chunks（按页切分，每页再细切）
        all_chunks = []
        chunk_metadata = []
        
        for page in pages:
            page_num = page['page_num']
            text = page['text']
            
            # 对长页面进行切分
            chunks = chunk_text(text, chunk_size=500, overlap=50)
            for chunk_idx, chunk_text_content in enumerate(chunks):
                all_chunks.append(chunk_text_content)
                chunk_metadata.append({
                    'page': page_num,
                    'chunk_idx': chunk_idx,
                    'text': chunk_text_content
                })
        
        if not all_chunks:
            return None
        
        # 3. 生成embeddings
        model = get_embedding_model()
        embeddings = model.encode(all_chunks, show_progress_bar=False)
        embeddings = np.array(embeddings).astype('float32')
        
        # 4. 创建FAISS索引
        dimension = embeddings.shape[1]
        index = faiss.IndexFlatIP(dimension)  # 使用内积作为相似度度量
        
        # L2归一化，使内积等价于余弦相似度
        faiss.normalize_L2(embeddings)
        index.add(embeddings)
        
        # 5. 保存FAISS索引
        faiss_path = _get_faiss_path(kb_dir, doc_id)
        faiss.write_index(index, faiss_path)
        
        # 6. 保存元数据
        meta_path = _get_meta_path(kb_dir, doc_id)
        doc_meta = {
            'doc_id': doc_id,
            'file_id': file_id,
            'file_name': file_name,
            'file_path': file_path,
            'page_count': len(pages),
            'chunk_count': len(all_chunks),
            'chunks': chunk_metadata,
            'created_at': now
        }
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(doc_meta, f, ensure_ascii=False, indent=2)
        
        # 7. 更新知识库元数据
        kb['documents'][doc_id] = {
            'doc_id': doc_id,
            'file_id': file_id,
            'file_name': file_name,
            'page_count': len(pages),
            'chunk_count': len(all_chunks),
            'created_at': now
        }
        kb['updated_at'] = now
        
        meta_path = os.path.join(kb_dir, 'kb_meta.json')
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(kb, f, ensure_ascii=False, indent=2)
        
        # 8. 更新文件记录，关联doc_id
        file_service.update_kb_file_doc_id(project_id, file_id, doc_id, len(pages))
        
        return {
            'doc_id': doc_id,
            'file_id': file_id,
            'file_name': file_name,
            'page_count': len(pages),
            'chunk_count': len(all_chunks),
            'status': 'ready'
        }
        
    except Exception as e:
        print(f"添加PDF到知识库失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def remove_pdf_from_kb(project_id: str, doc_id: str) -> bool:
    """
    从知识库中移除PDF文件
    
    同时删除对应的.faiss和.json文件
    """
    try:
        kb = get_kb(project_id)
        kb_dir = _get_kb_dir(project_id)
        
        if doc_id not in kb['documents']:
            return False
        
        # 删除FAISS文件
        faiss_path = _get_faiss_path(kb_dir, doc_id)
        if os.path.exists(faiss_path):
            os.remove(faiss_path)
        
        # 删除元数据文件
        meta_path = _get_meta_path(kb_dir, doc_id)
        if os.path.exists(meta_path):
            os.remove(meta_path)
        
        # 更新知识库元数据
        del kb['documents'][doc_id]
        kb['updated_at'] = datetime.now().isoformat()
        
        meta_path = os.path.join(kb_dir, 'kb_meta.json')
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(kb, f, ensure_ascii=False, indent=2)
        
        return True
        
    except Exception as e:
        print(f"移除PDF失败: {e}")
        return False


def list_kb_documents(project_id: str) -> List[Dict]:
    """
    获取知识库中的所有文档列表
    """
    kb = get_kb(project_id)
    if not kb or 'documents' not in kb:
        return []
    
    docs = []
    for doc_id, doc_info in kb['documents'].items():
        docs.append(doc_info)
    
    # 按创建时间倒序排列
    return sorted(docs, key=lambda x: x.get('created_at', ''), reverse=True)


def search_kb(project_id: str, query: str, top_k: int = 5) -> List[Dict]:
    """
    在知识库中搜索相关内容
    
    Args:
        project_id: 项目ID
        query: 查询文本
        top_k: 返回的最相似结果数量
    
    Returns:
        List[Dict]: 搜索结果，包含text, source, page, score
    """
    try:
        kb = get_kb(project_id)
        kb_dir = _get_kb_dir(project_id)
        
        if not kb or not kb.get('documents'):
            return []
        
        # 生成查询向量
        model = get_embedding_model()
        query_embedding = model.encode([query])
        query_embedding = np.array(query_embedding).astype('float32')
        faiss.normalize_L2(query_embedding)
        
        results = []
        
        # 在每个文档的索引中搜索
        for doc_id in kb['documents'].keys():
            faiss_path = _get_faiss_path(kb_dir, doc_id)
            meta_path = _get_meta_path(kb_dir, doc_id)
            
            if not os.path.exists(faiss_path) or not os.path.exists(meta_path):
                continue
            
            # 加载FAISS索引
            index = faiss.read_index(faiss_path)
            
            # 加载元数据
            with open(meta_path, 'r', encoding='utf-8') as f:
                doc_meta = json.load(f)
            
            # 搜索
            scores, indices = index.search(query_embedding, min(top_k, doc_meta['chunk_count']))
            
            # 收集结果
            for score, idx in zip(scores[0], indices[0]):
                if idx >= 0 and idx < len(doc_meta['chunks']):
                    chunk = doc_meta['chunks'][idx]
                    results.append({
                        'text': chunk['text'],
                        'source': doc_meta['file_name'],
                        'page': chunk['page'],
                        'score': float(score),
                        'doc_id': doc_id
                    })
        
        # 按相似度排序并返回top_k
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_k]
        
    except Exception as e:
        print(f"搜索知识库失败: {e}")
        import traceback
        traceback.print_exc()
        return []


def get_kb_stats(project_id: str) -> Dict:
    """
    获取知识库统计信息
    """
    kb = get_kb(project_id)
    if not kb:
        return {'document_count': 0, 'total_pages': 0, 'total_chunks': 0}
    
    documents = kb.get('documents', {})
    total_pages = sum(d.get('page_count', 0) for d in documents.values())
    total_chunks = sum(d.get('chunk_count', 0) for d in documents.values())
    
    return {
        'document_count': len(documents),
        'total_pages': total_pages,
        'total_chunks': total_chunks,
        'updated_at': kb.get('updated_at')
    }
