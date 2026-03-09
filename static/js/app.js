// Note Agent - 前端交互逻辑

// API 基础路径
const API_BASE = '/api';

// 状态管理
const state = {
    projects: [],
    currentProject: null,
    currentFile: null,
    currentChat: null,
    knowledgeBases: [],  // 保留兼容旧代码
    knowledgeBase: null,  // 新的单一知识库
    knowledgeBaseStats: {},
    files: [],
    messages: []
};

// 工具函数
async function fetchAPI(endpoint, options = {}) {
    const response = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            ...options.headers
        }
    });
    
    if (!response.ok) {
        const error = await response.json().catch(() => ({ error: '请求失败' }));
        throw new Error(error.error || '请求失败');
    }
    
    return response.json();
}

// 显示提示
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        top: 80px;
        right: 20px;
        padding: 12px 24px;
        background: ${type === 'success' ? '#22c55e' : type === 'error' ? '#ef4444' : '#6366f1'};
        color: white;
        border-radius: 8px;
        z-index: 1000;
        animation: slideIn 0.3s ease;
    `;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// 项目相关函数
async function loadProjects() {
    try {
        const data = await fetchAPI('/projects');
        state.projects = data.projects || [];
        renderProjects();
    } catch (error) {
        console.error('加载项目失败:', error);
        showToast('加载项目失败', 'error');
    }
}

function renderProjects() {
    const container = document.getElementById('projects-list');
    if (!container) return;
    
    if (state.projects.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">📁</div>
                <p>还没有项目</p>
                <p>点击上方"新建项目"开始</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = state.projects.map(project => `
        <div class="project-card">
            <div class="project-card-header" onclick="openProject('${project.id}')">
                <h3>${escapeHtml(project.name)}</h3>
                <p>${escapeHtml(project.description || '暂无描述')}</p>
            </div>
            <div class="project-meta" onclick="openProject('${project.id}')">
                <span>📄 ${project.file_count || 0} 文件</span>
                <span>💬 ${project.chat_count || 0} 对话</span>
            </div>
            <div class="project-actions">
                <button class="btn-delete" onclick="confirmDeleteProject('${project.id}', '${escapeHtml(project.name)}')" title="删除项目">🗑️</button>
            </div>
        </div>
    `).join('');
}

function showCreateProjectModal() {
    const modal = document.getElementById('create-project-modal');
    if (modal) {
        modal.classList.add('active');
    }
}

function hideCreateProjectModal() {
    const modal = document.getElementById('create-project-modal');
    if (modal) {
        modal.classList.remove('active');
        // 清空表单
        document.getElementById('project-name').value = '';
        document.getElementById('project-desc').value = '';
    }
}

async function createProject() {
    const name = document.getElementById('project-name').value.trim();
    const description = document.getElementById('project-desc').value.trim();
    
    if (!name) {
        showToast('请输入项目名称', 'error');
        return;
    }
    
    try {
        await fetchAPI('/projects', {
            method: 'POST',
            body: JSON.stringify({ name, description })
        });
        
        showToast('项目创建成功', 'success');
        hideCreateProjectModal();
        loadProjects();
    } catch (error) {
        showToast(error.message, 'error');
    }
}

async function openProject(projectId) {
    window.location.href = `/project/${projectId}`;
}

// 显示删除确认
function confirmDeleteProject(projectId, projectName) {
    if (confirm(`确定要删除项目 "${projectName}" 吗？\n\n删除后将无法恢复，项目内的所有文件和知识库也将被删除。`)) {
        deleteProject(projectId);
    }
}

// 删除项目
async function deleteProject(projectId) {
    try {
        await fetchAPI(`/projects/${projectId}`, {
            method: 'DELETE'
        });
        
        showToast('项目删除成功', 'success');
        loadProjects(); // 刷新项目列表
    } catch (error) {
        showToast(error.message || '删除项目失败', 'error');
    }
}

// 文件相关函数
async function loadFiles(projectId) {
    try {
        const data = await fetchAPI(`/projects/${projectId}/files`);
        state.files = data.files || [];
        renderFiles();
    } catch (error) {
        console.error('加载文件失败:', error);
        showToast('加载文件失败', 'error');
    }
}

function renderFiles() {
    const container = document.querySelector('.file-list');
    if (!container) return;
    
    if (state.files.length === 0) {
        container.innerHTML = `
            <li class="empty-state">
                <div class="empty-icon">📄</div>
                <p>暂无文件</p>
            </li>
        `;
        return;
    }
    
    container.innerHTML = state.files.map(file => `
        <li class="file-item ${state.currentFile?.id === file.id ? 'active' : ''}" 
            onclick="selectFile('${file.id}')">
            <span class="file-icon">${getFileIcon(file.type)}</span>
            <span class="file-name">${escapeHtml(file.name)}</span>
        </li>
    `).join('');
}

function getFileIcon(type) {
    const icons = {
        'pdf': '📕',
        'text': '📝',
        'md': '📝',
        'txt': '📄',
        'json': '📋',
        'image': '🖼️',
        'default': '📄'
    };
    return icons[type] || icons['default'];
}

async function selectFile(fileId) {
    const file = state.files.find(f => f.id === fileId);
    if (!file) return;
    
    state.currentFile = file;
    renderFiles();
    
    try {
        const projectId = state.currentProject?.id;
        if (!projectId) return;
        const data = await fetchAPI(`/projects/${projectId}/files/${fileId}`);
        renderFilePreview(data.file || data);
    } catch (error) {
        showToast('加载文件内容失败', 'error');
    }
}

function renderFilePreview(data) {
    const container = document.querySelector('.preview-content');
    if (!container) return;
    
    // 根据文件类型或扩展名渲染
    const isMarkdown = data.type === 'md' || data.type === 'markdown' || 
                       data.name?.endsWith('.md') || data.name?.endsWith('.markdown');
    
    if (isMarkdown) {
        // Markdown 渲染
        container.innerHTML = `<div class="markdown-content">${renderMarkdown(data.content)}</div>`;
    } else if (data.type === 'text' || data.name?.endsWith('.txt') || data.name?.endsWith('.json')) {
        // 纯文本
        container.innerHTML = `<pre class="text-content">${escapeHtml(data.content)}</pre>`;
    } else if (data.type === 'pdf') {
        // PDF 预览
        container.innerHTML = `<div class="pdf-preview">PDF 预览: ${escapeHtml(data.name)}</div>`;
    } else if (data.type === 'image') {
        // 图片预览
        container.innerHTML = `<img src="/uploads/${data.path?.split('/').pop()}" alt="${escapeHtml(data.name)}" style="max-width: 100%;">`;
    } else {
        // 其他类型
        container.innerHTML = `<div class="file-info">文件: ${escapeHtml(data.name)}<br>类型: ${data.type}</div>`;
    }
}

// 聊天相关函数
async function loadMessages(chatId) {
    try {
        const data = await fetchAPI(`/chats/${chatId}/messages`);
        state.messages = data.messages || [];
        renderMessages();
    } catch (error) {
        console.error('加载消息失败:', error);
    }
}

function renderMessages() {
    const container = document.querySelector('.chat-messages');
    if (!container) return;
    
    if (state.messages.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">💬</div>
                <p>开始对话吧</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = state.messages.map(msg => `
        <div class="message ${msg.role}">
            ${msg.role === 'user' ? escapeHtml(msg.content) : renderMarkdown(msg.content)}
        </div>
    `).join('');
    
    // 滚动到底部
    container.scrollTop = container.scrollHeight;
}

async function sendMessage() {
    const input = document.querySelector('.chat-input');
    const content = input.value.trim();
    
    if (!content) return;
    
    // 添加用户消息
    state.messages.push({ role: 'user', content });
    renderMessages();
    input.value = '';
    
    try {
        const data = await fetchAPI(`/chats/${state.currentChat}/messages`, {
            method: 'POST',
            body: JSON.stringify({ content })
        });
        
        // 添加助手回复
        state.messages.push({ role: 'assistant', content: data.response });
        renderMessages();
        
        // 检查是否有变更提案
        if (data.proposal) {
            renderProposal(data.proposal);
        }
    } catch (error) {
        showToast(error.message, 'error');
        // 移除失败的用户消息
        state.messages.pop();
        renderMessages();
    }
}

function renderProposal(proposal) {
    const container = document.querySelector('.panel-content');
    if (!container) return;
    
    const proposalHtml = `
        <div class="proposal-card">
            <div class="proposal-header">
                <span class="proposal-icon">📝</span>
                <span class="proposal-title">${proposal.operation === 'create' ? '创建文件' : '修改文件'}: ${escapeHtml(proposal.filename)}</span>
            </div>
            <div class="proposal-diff">
                ${proposal.diff || ''}
            </div>
            <div class="proposal-actions">
                <button class="btn btn-success btn-small" onclick="applyProposal('${proposal.id}')">应用</button>
                <button class="btn btn-secondary btn-small" onclick="rejectProposal('${proposal.id}')">拒绝</button>
            </div>
        </div>
    `;
    
    container.insertAdjacentHTML('beforeend', proposalHtml);
}

async function applyProposal(proposalId) {
    try {
        await fetchAPI(`/proposals/${proposalId}/apply`, { method: 'POST' });
        showToast('变更已应用', 'success');
        // 刷新文件列表
        if (state.currentProject) {
            loadFiles(state.currentProject.id);
        }
    } catch (error) {
        showToast(error.message, 'error');
    }
}

async function rejectProposal(proposalId) {
    try {
        await fetchAPI(`/proposals/${proposalId}/reject`, { method: 'POST' });
        showToast('已拒绝变更', 'info');
    } catch (error) {
        showToast(error.message, 'error');
    }
}

// 知识库相关函数（兼容新接口，每个项目只有一个知识库）
async function loadKnowledgeBases(projectId) {
    try {
        const data = await fetchAPI(`/projects/${projectId}/kb`);
        // 新接口返回的是单个知识库信息
        if (data.kb) {
            state.knowledgeBase = data.kb;
            state.knowledgeBaseStats = data.kb.stats || {};
        }
        renderKnowledgeBases();
    } catch (error) {
        console.error('加载知识库失败:', error);
        // 如果404，说明知识库还没创建，这是正常的
        if (error.message && error.message.includes('404')) {
            state.knowledgeBase = null;
            renderKnowledgeBases();
        }
    }
}

function renderKnowledgeBases() {
    const container = document.querySelector('.kb-list');
    if (!container) return;
    
    // 如果没有知识库数据，显示空状态
    if (!state.knowledgeBase) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">📚</div>
                <p>知识库为空</p>
                <p class="hint">上传PDF文件到知识库</p>
            </div>
        `;
        return;
    }
    
    const stats = state.knowledgeBaseStats || {};
    container.innerHTML = `
        <div class="kb-info">
            <div class="kb-stats">
                <span class="stat">📄 ${stats.document_count || 0} 个文档</span>
                <span class="stat">📑 ${stats.total_pages || 0} 页</span>
            </div>
            <p class="kb-hint">知识库已就绪，可以直接询问文档内容</p>
        </div>
    `;
}

// Markdown 简单渲染
function renderMarkdown(text) {
    if (!text) return '';
    
    // 简单的 Markdown 渲染
    return text
        // 代码块
        .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>')
        // 行内代码
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        // 标题
        .replace(/^### (.+)$/gm, '<h3>$1</h3>')
        .replace(/^## (.+)$/gm, '<h2>$1</h2>')
        .replace(/^# (.+)$/gm, '<h1>$1</h1>')
        // 粗体和斜体
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        // 链接
        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
        // 换行
        .replace(/\n/g, '<br>');
}

// HTML 转义
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 键盘事件处理
document.addEventListener('keydown', (e) => {
    // Enter 发送消息
    if (e.key === 'Enter' && !e.shiftKey) {
        const chatInput = document.querySelector('.chat-input');
        if (chatInput && document.activeElement === chatInput) {
            e.preventDefault();
            sendMessage();
        }
    }
    
    // Escape 关闭模态框
    if (e.key === 'Escape') {
        hideCreateProjectModal();
    }
});

// 页面初始化
document.addEventListener('DOMContentLoaded', () => {
    // 如果在首页，加载项目列表
    if (document.getElementById('projects-list')) {
        loadProjects();
    }
    
    // 如果在工作台页面，初始化工作台
    if (document.querySelector('.workspace')) {
        initWorkspace();
    }
});

// 初始化工作台
function initWorkspace() {
    const projectId = document.body.dataset.projectId;
    if (projectId) {
        state.currentProject = { id: projectId };
        loadFiles(projectId);
        loadKnowledgeBases(projectId);
    }
}

// 导出函数供全局使用
window.showCreateProjectModal = showCreateProjectModal;
window.hideCreateProjectModal = hideCreateProjectModal;
window.createProject = createProject;
window.openProject = openProject;
window.selectFile = selectFile;
window.sendMessage = sendMessage;
window.applyProposal = applyProposal;
window.rejectProposal = rejectProposal;
window.confirmDeleteProject = confirmDeleteProject;
window.deleteProject = deleteProject;