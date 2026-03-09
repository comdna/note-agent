// 项目工作台 JavaScript

// 全局状态
let currentChatId = null;
let isGenerating = false;  // 是否正在生成回复
let abortController = null;  // 用于中断流式请求
let currentFileData = null;
let isEditingFile = false;
let originalFileContent = '';
const stepsByMessageId = {};

// DOM 加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    initProject();
    initTabs();
    initUpload();
    initKBUpload();
    initChatInput();
    loadChats();  // 加载对话列表
});

// 初始化项目
function initProject() {
    loadProjectInfo();
    loadFiles();
    loadKBFiles();
}

// 初始化标签页切换
function initTabs() {
    document.querySelectorAll('.panel-tabs').forEach(tabGroup => {
        tabGroup.addEventListener('click', (e) => {
            if (e.target.classList.contains('tab-btn')) {
                const tab = e.target.dataset.tab;
                const panel = e.target.closest('aside, .panel-tabs').parentElement || e.target.closest('.panel-tabs').nextElementSibling;
                
                // 切换按钮状态
                tabGroup.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
                e.target.classList.add('active');
                
                // 切换内容
                if (panel) {
                    panel.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
                    const contentEl = panel.querySelector(`#${tab}-tab`);
                    if (contentEl) contentEl.classList.add('active');
                }
            }
        });
    });
}

// 初始化聊天输入框
function initChatInput() {
    const textarea = document.getElementById('chat-input');
    if (textarea) {
        // 自动调整高度
        textarea.addEventListener('input', () => {
            textarea.style.height = 'auto';
            textarea.style.height = Math.min(textarea.scrollHeight, 150) + 'px';
        });
    }
}

// ==================== 对话管理 ====================

// 加载对话列表
async function loadChats() {
    try {
        const response = await fetch(`/api/projects/${PROJECT_ID}/chats`);
        const container = document.getElementById('chat-list');
        
        if (!container) return;
        
        if (response.ok) {
            const data = await response.json();
            const chats = data.chats || [];
            
            if (chats.length === 0) {
                // 如果没有对话，自动创建一个
                await createNewChat();
                return;
            }
            
            renderChatList(chats);
            
            // 如果没有当前选中的对话，选中第一个
            if (!currentChatId && chats.length > 0) {
                selectChat(chats[0].id);
            }
        } else {
            container.innerHTML = '<div class="empty-state">加载失败</div>';
        }
    } catch (err) {
        console.error('加载对话列表失败:', err);
        document.getElementById('chat-list').innerHTML = '<div class="empty-state">加载失败</div>';
    }
}

// 渲染对话列表
function renderChatList(chats) {
    const container = document.getElementById('chat-list');
    if (!container) return;
    
    container.innerHTML = chats.map(chat => `
        <div class="chat-item ${chat.id === currentChatId ? 'active' : ''}" data-chat-id="${chat.id}">
            <div class="chat-info" onclick="selectChat('${chat.id}')">
                <span class="chat-icon">💬</span>
                <span class="chat-title">${escapeHtml(chat.title || '未命名对话')}</span>
            </div>
            <button class="btn-delete-chat" onclick="event.stopPropagation(); confirmDeleteChat('${chat.id}', '${escapeHtml(chat.title || '未命名对话')}')" title="删除对话">🗑️</button>
        </div>
    `).join('');
}

// 选择对话
async function selectChat(chatId) {
    if (isGenerating) {
        // 如果正在生成，提示用户
        if (!confirm('正在生成回复中，切换对话将中断当前生成。是否继续？')) {
            return;
        }
        stopGeneration();
    }
    
    currentChatId = chatId;
    
    // 更新UI选中状态
    document.querySelectorAll('.chat-item').forEach(item => {
        item.classList.toggle('active', item.dataset.chatId === chatId);
    });
    
    // 加载对话消息
    await loadChatMessages(chatId);
}

// 加载对话消息
async function loadChatMessages(chatId) {
    try {
        const response = await fetch(`/api/projects/${PROJECT_ID}/chats/${chatId}`);
        if (response.ok) {
            const data = await response.json();
            const chat = data.chat || data;
            renderMessages(chat.messages || []);
        }
    } catch (err) {
        console.error('加载对话消息失败:', err);
    }
}

// 渲染消息列表
function renderMessages(messages) {
    const container = document.getElementById('chat-messages');
    if (!container) return;
    
    if (messages.length === 0) {
        container.innerHTML = `
            <div class="welcome-message">
                <h3>👋 欢迎来到项目工作台</h3>
                <p>你可以问我关于项目资料的问题，或让我帮你整理笔记</p>
                <p class="hint-text">💡 提示：上传PDF到右侧知识库后，可以直接询问文档内容</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = '';
    messages.forEach(msg => {
        if (msg.role === 'user') {
            addMessageToUI(msg.content, 'user', false);
        } else if (msg.role === 'assistant') {
            let content = msg.content;
            // 添加知识库标记
            if (msg.used_kb) {
                content += '\n\n📚（基于知识库回答）';
            }
            addMessageToUI(content, 'assistant', false, msg.steps || []);
        }
    });
    
    // 滚动到底部
    container.scrollTop = container.scrollHeight;
}

// 创建新对话
async function createNewChat() {
    if (isGenerating) {
        alert('请等待当前回复完成后再创建新对话');
        return;
    }
    
    try {
        const response = await fetch(`/api/projects/${PROJECT_ID}/chats`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: '新对话' })
        });
        
        if (response.ok) {
            const data = await response.json();
            const chat = data.chat || data;
            
            // 重新加载对话列表
            await loadChats();
            
            // 选中新创建的对话
            selectChat(chat.id);
        } else {
            alert('创建对话失败');
        }
    } catch (err) {
        console.error('创建对话失败:', err);
        alert('创建对话失败: ' + err.message);
    }
}

// 确认删除对话
function confirmDeleteChat(chatId, chatTitle) {
    if (isGenerating && currentChatId === chatId) {
        alert('请等待当前回复完成后再删除对话');
        return;
    }
    
    if (confirm(`确定要删除对话 "${chatTitle}" 吗？\n\n删除后将无法恢复。`)) {
        deleteChat(chatId);
    }
}

// 删除对话
async function deleteChat(chatId) {
    try {
        const response = await fetch(`/api/projects/${PROJECT_ID}/chats/${chatId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            // 如果删除的是当前对话，清空当前对话ID
            if (currentChatId === chatId) {
                currentChatId = null;
                // 清空消息显示
                const container = document.getElementById('chat-messages');
                if (container) {
                    container.innerHTML = `
                        <div class="welcome-message">
                            <h3>👋 欢迎来到项目工作台</h3>
                            <p>你可以问我关于项目资料的问题，或让我帮你整理笔记</p>
                            <p class="hint-text">💡 提示：上传PDF到右侧知识库后，可以直接询问文档内容</p>
                        </div>
                    `;
                }
            }
            // 重新加载对话列表
            await loadChats();
        } else {
            alert('删除对话失败');
        }
    } catch (err) {
        console.error('删除对话失败:', err);
        alert('删除对话失败: ' + err.message);
    }
}

// ==================== 普通文件上传功能 ====================

// 初始化上传功能
function initUpload() {
    const dropZone = document.getElementById('upload-drop-zone');
    const fileInput = document.getElementById('file-input');
    
    if (dropZone && fileInput) {
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });
        
        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('dragover');
        });
        
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            handleFiles(e.dataTransfer.files, 'upload-preview');
        });
        
        fileInput.addEventListener('change', (e) => {
            handleFiles(e.target.files, 'upload-preview');
        });
    }
}

// 处理文件选择
function handleFiles(files, previewId) {
    const preview = document.getElementById(previewId);
    if (!preview) return;
    
    preview.innerHTML = '';
    for (const file of files) {
        const item = document.createElement('div');
        item.className = 'upload-item';
        item.innerHTML = `
            <span class="file-name">${file.name}</span>
            <span class="file-size">${formatFileSize(file.size)}</span>
        `;
        preview.appendChild(item);
    }
}

// 格式化文件大小
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function getFileExtension(filename) {
    if (!filename || filename.indexOf('.') === -1) return '';
    return filename.split('.').pop().toLowerCase();
}

function isMarkdownFile(file) {
    const ext = getFileExtension(file.name);
    return ext === 'md' || ext === 'markdown';
}

function isEditableFile(file) {
    if (!file) return false;
    if (file.type === 'text') return true;
    const ext = getFileExtension(file.name);
    return ['txt', 'md', 'markdown', 'json', 'py', 'js', 'html', 'css'].includes(ext);
}

function hasUnsavedChanges() {
    if (!isEditingFile) return false;
    const editor = document.getElementById('file-editor');
    if (!editor) return false;
    return editor.value !== (originalFileContent ?? '');
}

// 显示/隐藏普通文件上传模态框
function showUploadModal() {
    document.getElementById('upload-modal').classList.add('active');
}

function hideUploadModal() {
    document.getElementById('upload-modal').classList.remove('active');
    // 清空预览
    document.getElementById('upload-preview').innerHTML = '';
    document.getElementById('file-input').value = '';
}

// 上传普通文件
async function uploadFiles() {
    const fileInput = document.getElementById('file-input');
    if (!fileInput.files.length) {
        alert('请选择文件');
        return;
    }
    
    const formData = new FormData();
    for (const file of fileInput.files) {
        formData.append('files', file);
    }
    
    try {
        const response = await fetch(`/api/projects/${PROJECT_ID}/files`, {
            method: 'POST',
            body: formData
        });
        
        if (response.ok) {
            const data = await response.json();
            const uploadedCount = data.files ? data.files.length : 1;
            alert(`成功上传 ${uploadedCount} 个文件`);
            hideUploadModal();
            loadFiles();
        } else {
            const err = await response.json();
            alert(err.error || '上传失败');
        }
    } catch (err) {
        console.error('上传失败:', err);
        alert('上传失败: ' + err.message);
    }
}

// ==================== 知识库PDF上传功能 ====================

// 初始化知识库上传功能
function initKBUpload() {
    const dropZone = document.getElementById('kb-upload-drop-zone');
    const fileInput = document.getElementById('kb-file-input');
    
    if (dropZone && fileInput) {
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });
        
        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('dragover');
        });
        
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            // 只接受PDF文件
            const files = Array.from(e.dataTransfer.files).filter(f => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf'));
            if (files.length < e.dataTransfer.files.length) {
                alert('知识库只接受PDF文件');
            }
            if (files.length > 0) {
                handleFiles(files, 'kb-upload-preview');
            }
        });
        
        fileInput.addEventListener('change', (e) => {
            handleFiles(e.target.files, 'kb-upload-preview');
        });
    }
}

// 显示/隐藏知识库上传模态框
function showKBUploadModal() {
    document.getElementById('kb-upload-modal').classList.add('active');
}

function hideKBUploadModal() {
    document.getElementById('kb-upload-modal').classList.remove('active');
    // 清空预览
    document.getElementById('kb-upload-preview').innerHTML = '';
    document.getElementById('kb-file-input').value = '';
}

// 上传PDF到知识库
async function uploadKBFiles() {
    const fileInput = document.getElementById('kb-file-input');
    if (!fileInput.files.length) {
        alert('请选择PDF文件');
        return;
    }
    
    // 验证都是PDF文件
    for (const file of fileInput.files) {
        if (!file.name.toLowerCase().endsWith('.pdf')) {
            alert('知识库只接受PDF文件: ' + file.name);
            return;
        }
    }
    
    const formData = new FormData();
    for (const file of fileInput.files) {
        formData.append('files', file);
    }
    
    try {
        const response = await fetch(`/api/projects/${PROJECT_ID}/kb/files`, {
            method: 'POST',
            body: formData
        });
        
        if (response.ok) {
            const data = await response.json();
            const files = data.files || [data.file];
            
            // 显示处理结果
            let successCount = 0;
            let failCount = 0;
            files.forEach(f => {
                if (f.kb_status === 'indexed') {
                    successCount++;
                } else {
                    failCount++;
                }
            });
            
            let msg = `上传完成！\n成功建立索引: ${successCount} 个`;
            if (failCount > 0) {
                msg += `\n失败: ${failCount} 个`;
            }
            alert(msg);
            
            hideKBUploadModal();
            loadKBFiles();
        } else {
            const err = await response.json();
            alert(err.error || '上传失败');
        }
    } catch (err) {
        console.error('上传知识库文件失败:', err);
        alert('上传失败: ' + err.message);
    }
}

// ==================== 文件列表功能 ====================

// 加载普通文件列表
async function loadFiles() {
    try {
        const response = await fetch(`/api/projects/${PROJECT_ID}/files`);
        const container = document.getElementById('file-list');
        
        if (!container) return;
        
        if (response.ok) {
            const data = await response.json();
            const files = data.files || [];
            if (files.length === 0) {
                container.innerHTML = '<div class="empty-state">暂无文件<br><small>点击 + 上传 txt, md, 代码, 图片等</small></div>';
                return;
            }
            
            container.innerHTML = files.map(file => `
                <div class="file-item" data-file-id="${file.id}">
                    <div class="file-info" onclick="selectFile('${file.id}')">
                        <span class="file-icon">${getFileIcon(file.type)}</span>
                        <span class="file-name">${escapeHtml(file.name)}</span>
                    </div>
                    <button class="btn-delete-file" onclick="event.stopPropagation(); confirmDeleteFile('${file.id}', '${escapeHtml(file.name)}', false)" title="删除文件">🗑️</button>
                </div>
            `).join('');
        } else {
            container.innerHTML = '<div class="empty-state">加载失败</div>';
        }
    } catch (err) {
        console.error('加载文件失败:', err);
        document.getElementById('file-list').innerHTML = '<div class="empty-state">加载失败</div>';
    }
}

// 加载知识库PDF文件列表
async function loadKBFiles() {
    try {
        const response = await fetch(`/api/projects/${PROJECT_ID}/kb/files`);
        const container = document.getElementById('kb-file-list');
        const statsContainer = document.getElementById('kb-stats');
        
        if (!container) return;
        
        if (response.ok) {
            const data = await response.json();
            const files = data.files || [];
            
            // 更新统计
            const totalPages = files.reduce((sum, f) => sum + (f.page_count || 0), 0);
            document.getElementById('kb-doc-count').textContent = files.length;
            document.getElementById('kb-page-count').textContent = totalPages;
            
            if (files.length === 0) {
                container.innerHTML = '<div class="empty-state">暂无PDF文档<br><small>点击"上传PDF"添加文档到知识库</small></div>';
                return;
            }
            
            container.innerHTML = files.map(file => `
                <div class="kb-file-item" data-file-id="${file.id}">
                    <div class="kb-file-info">
                        <span class="file-icon">📄</span>
                        <div class="kb-file-details">
                            <span class="file-name">${escapeHtml(file.name)}</span>
                            <span class="file-meta">${file.page_count || 0} 页</span>
                        </div>
                    </div>
                    <button class="btn-delete-file" onclick="confirmDeleteFile('${file.id}', '${escapeHtml(file.name)}', true)" title="删除">🗑️</button>
                </div>
            `).join('');
        } else {
            container.innerHTML = '<div class="empty-state">加载失败</div>';
        }
    } catch (err) {
        console.error('加载知识库文件失败:', err);
        document.getElementById('kb-file-list').innerHTML = '<div class="empty-state">加载失败</div>';
    }
}

// 确认删除文件
function confirmDeleteFile(fileId, fileName, isKBFile) {
    const type = isKBFile ? 'PDF文档' : '文件';
    if (confirm(`确定要删除${type} "${fileName}" 吗？\n\n删除后将无法恢复。${isKBFile ? '同时会删除知识库索引。' : ''}`)) {
        if (isKBFile) {
            deleteKBFile(fileId);
        } else {
            deleteFile(fileId);
        }
    }
}

// 删除普通文件
async function deleteFile(fileId) {
    try {
        const response = await fetch(`/api/projects/${PROJECT_ID}/files/${fileId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            loadFiles();
            // 清空预览区
            currentFileData = null;
            isEditingFile = false;
            originalFileContent = '';
            const previewArea = document.getElementById('preview-area');
            if (previewArea) {
                previewArea.innerHTML = `
                    <div class="preview-placeholder">
                        <div class="placeholder-icon">📄</div>
                        <p>选择左侧文件开始预览</p>
                    </div>
                `;
            }
        } else {
            const err = await response.json();
            alert(err.error || '删除失败');
        }
    } catch (err) {
        console.error('删除文件失败:', err);
        alert('删除文件失败');
    }
}

// 删除知识库文件
async function deleteKBFile(fileId) {
    try {
        const response = await fetch(`/api/projects/${PROJECT_ID}/kb/files/${fileId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            loadKBFiles();
        } else {
            const err = await response.json();
            alert(err.error || '删除失败');
        }
    } catch (err) {
        console.error('删除知识库文件失败:', err);
        alert('删除知识库文件失败');
    }
}

// 获取文件图标
function getFileIcon(type) {
    if (type?.includes('pdf')) return '📄';
    if (type?.includes('image')) return '🖼️';
    if (type?.includes('text') || type?.includes('markdown')) return '📝';
    return '📎';
}

// 选择文件
async function selectFile(fileId) {
    if (isEditingFile && hasUnsavedChanges()) {
        const proceed = confirm('当前文件有未保存的修改，确定要切换吗？');
        if (!proceed) return;
    }
    isEditingFile = false;

    // 标记选中状态
    document.querySelectorAll('.file-item').forEach(item => item.classList.remove('active'));
    const currentItem = document.querySelector(`.file-item[data-file-id="${fileId}"]`);
    if (currentItem) currentItem.classList.add('active');
    
    // 加载文件预览
    try {
        const response = await fetch(`/api/projects/${PROJECT_ID}/files/${fileId}`);
        if (response.ok) {
            const data = await response.json();
            const fileData = data.file || data;
            currentFileData = fileData;
            originalFileContent = fileData.content || '';
            renderFilePreview(fileData);
        }
    } catch (err) {
        console.error('加载文件预览失败:', err);
    }
}

// 渲染文件预览
function renderFilePreview(file) {
    const container = document.getElementById('preview-area');
    if (!container) return;

    currentFileData = file;
    isEditingFile = false;
    originalFileContent = file.content || '';

    const title = escapeHtml(file.name || '未命名文件');
    const isMarkdown = isMarkdownFile(file);
    const ext = getFileExtension(file.name);
    const isText = file.type === 'text' || ext === 'txt' || ext === 'json';
    const isCode = ['py', 'js', 'html', 'css'].includes(ext);
    const editable = isEditableFile(file);
    const storedName = file.path ? file.path.split(/[/\\]/).pop() : file.name;
    const imageUrl = storedName ? `/uploads/${PROJECT_ID}/${encodeURIComponent(storedName)}` : '';


    if (editable) {
        let bodyHtml = '';
        if (isMarkdown) {
            bodyHtml = `<div class="markdown-preview">${renderMarkdown(file.content || '')}</div>`;
        } else if (isText || isCode) {
            bodyHtml = `<pre class="text-preview">${escapeHtml(file.content || '')}</pre>`;
        } else {
            bodyHtml = `<div class="file-info">📎 ${title}<p>该文件类型暂不支持预览</p></div>`;
        }
        container.innerHTML = `
            <div class="file-preview">
                <div class="preview-toolbar">
                    <div class="preview-title">${title}</div>
                    <div class="preview-actions">
                        <button class="btn btn-secondary btn-small" onclick="startEditFile()">编辑</button>
                    </div>
                </div>
                <div class="preview-body">${bodyHtml}</div>
            </div>
        `;
        return;
    }

    if (file.type === 'image') {
        container.innerHTML = `
            <div class="file-preview">
                <div class="preview-toolbar">
                    <div class="preview-title">${title}</div>
                </div>
                <div class="preview-body">
                    <img src="${imageUrl}" alt="${title}" style="max-width: 100%; max-height: 100%;">
                </div>
            </div>
        `;
    } else {
        container.innerHTML = `
            <div class="file-preview">
                <div class="preview-toolbar">
                    <div class="preview-title">${title}</div>
                </div>
                <div class="file-info">📎 ${title}<p>该文件类型暂不支持预览</p></div>
            </div>
        `;
    }
}

function renderFileEditor(file) {
    const container = document.getElementById('preview-area');
    if (!container) return;

    currentFileData = file;
    isEditingFile = true;
    originalFileContent = file.content || '';

    const title = escapeHtml(file.name || '未命名文件');
    container.innerHTML = `
        <div class="file-preview editing">
            <div class="preview-toolbar">
                <div class="preview-title">${title}</div>
                <div class="preview-actions">
                    <button class="btn btn-primary btn-small" onclick="saveCurrentFile()">保存</button>
                    <button class="btn btn-secondary btn-small" onclick="cancelEditFile()">取消</button>
                </div>
            </div>
            <textarea id="file-editor" class="file-editor" spellcheck="false"></textarea>
        </div>
    `;
    const editor = document.getElementById('file-editor');
    if (editor) {
        editor.value = file.content || '';
        editor.focus();
    }
}

function startEditFile() {
    if (!currentFileData) return;
    if (!isEditableFile(currentFileData)) {
        alert('该文件类型暂不支持编辑');
        return;
    }
    renderFileEditor(currentFileData);
}

function cancelEditFile() {
    if (!currentFileData) return;
    if (hasUnsavedChanges()) {
        const proceed = confirm('当前修改尚未保存，确定要取消吗？');
        if (!proceed) return;
    }
    renderFilePreview(currentFileData);
}

async function saveCurrentFile() {
    if (!currentFileData) return;
    const editor = document.getElementById('file-editor');
    if (!editor) return;

    const newContent = editor.value;
    try {
        const response = await fetch(`/api/projects/${PROJECT_ID}/files/${currentFileData.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: newContent })
        });

        if (!response.ok) {
            const err = await response.json();
            alert(err.error || '保存失败');
            return;
        }

        const data = await response.json();
        const updated = data.file || data;
        currentFileData.content = newContent;
        currentFileData.updated_at = updated.updated_at || currentFileData.updated_at;
        originalFileContent = newContent;
        renderFilePreview(currentFileData);
        alert('保存成功');
    } catch (err) {
        console.error('保存文件失败:', err);
        alert('保存失败: ' + err.message);
    }
}

// Markdown 简单渲染
function renderMarkdown(text) {
    if (!text) return '';
    return text
        .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/^### (.+)$/gm, '<h3>$1</h3>')
        .replace(/^## (.+)$/gm, '<h2>$1</h2>')
        .replace(/^# (.+)$/gm, '<h1>$1</h1>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
        .replace(/\n/g, '<br>');
}

// HTML 转义
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function renderStepsHTML(steps) {
    if (!steps || steps.length === 0) return '';
    const items = steps.map(step => {
        const tool = escapeHtml(step.tool || 'tool');
        const result = escapeHtml(step.result || '');
        return `<div class="step-item"><span class="step-tool">${tool}</span><span class="step-result">${result}</span></div>`;
    }).join('');
    return `<div class="steps-panel"><div class="steps-title">🔧 Tool Trace</div>${items}</div>`;
}

// ==================== 项目信息 ====================

// 加载项目信息
async function loadProjectInfo() {
    try {
        const response = await fetch(`/api/projects/${PROJECT_ID}`);
        if (response.ok) {
            const data = await response.json();
            const project = data.project || data;
            document.getElementById('project-title').textContent = project.name || '未命名项目';
        }
    } catch (err) {
        console.error('加载项目信息失败:', err);
        document.getElementById('project-title').textContent = '未命名项目';
    }
}

// 刷新文件列表
function refreshFiles() {
    loadFiles();
}

// ==================== 聊天功能 ====================

// 显示文件选择器
function showFileSelector() {
    console.log('显示文件选择器');
}

// 清空聊天
function clearChat() {
    const container = document.getElementById('chat-messages');
    if (container) {
        container.innerHTML = `
            <div class="welcome-message">
                <h3>👋 欢迎来到项目工作台</h3>
                <p>你可以问我关于项目资料的问题，或让我帮你整理笔记</p>
                <p class="hint-text">💡 提示：上传PDF到右侧知识库后，可以直接询问文档内容</p>
            </div>
        `;
    }
}

// 停止生成
function stopGeneration() {
    if (abortController) {
        abortController.abort();
        abortController = null;
    }
    isGenerating = false;
    updateInputState();
}

// 更新输入框状态
function updateInputState() {
    const input = document.getElementById('chat-input');
    const sendBtn = document.querySelector('.btn-send');
    
    if (input) {
        input.disabled = isGenerating;
        input.placeholder = isGenerating ? '等待回复完成...' : '输入你的问题...（例如：我的资料里讲了什么？）';
    }
    
    if (sendBtn) {
        sendBtn.textContent = isGenerating ? '⏹' : '➤';
        sendBtn.onclick = isGenerating ? stopGeneration : sendMessage;
        sendBtn.classList.toggle('stop', isGenerating);
    }
}

// 发送消息（流式）
async function sendMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    
    if (!message) return;
    
    // 确保有当前对话
    if (!currentChatId) {
        await createNewChat();
        if (!currentChatId) return;
    }
    
    // 添加用户消息到UI
    addMessageToUI(message, 'user', true);
    input.value = '';
    input.style.height = 'auto';
    
    // 设置生成状态
    isGenerating = true;
    updateInputState();
    
    // 创建AI消息占位符（用于流式显示）
    const aiMessageId = 'msg-' + Date.now();
    const aiMessageEl = createAIMessagePlaceholder(aiMessageId);
    
    try {
        abortController = new AbortController();
        
        const response = await fetch(`/api/projects/${PROJECT_ID}/chats/${currentChatId}/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                content: message,
                use_web: document.getElementById('web-search-toggle')?.checked
            }),
            signal: abortController.signal
        });
        
        if (!response.ok) {
            throw new Error('请求失败');
        }
        
        // 读取SSE流
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let fullContent = '';
        let citations = [];
        let usedKb = false;
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();  // 保留不完整的行
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        
                        switch (data.type) {
                            case 'start':
                                // 开始生成
                                break;
                            case 'delta':
                                // 内容片段
                                fullContent += data.content;
                                updateAIMessage(aiMessageId, fullContent, citations, usedKb, false, stepsByMessageId[aiMessageId] || null);
                                break;
                            case 'citations':
                                // 引用信息
                                citations = data.citations || [];
                                break;
                            case 'steps':
                                stepsByMessageId[aiMessageId] = data.steps || [];
                                updateAIMessage(aiMessageId, fullContent, citations, usedKb, false, stepsByMessageId[aiMessageId]);
                                break;
                            case 'end':
                                // 完成
                                break;
                            case 'error':
                                throw new Error(data.error || '生成出错');
                        }
                    } catch (e) {
                        console.error('解析SSE数据失败:', e);
                    }
                }
            }
        }
        
        // 最终更新
        updateAIMessage(aiMessageId, fullContent, citations, usedKb, true, stepsByMessageId[aiMessageId] || null);
        
    } catch (err) {
        if (err.name === 'AbortError') {
            // 用户中断
            updateAIMessage(aiMessageId, fullContent + '\n\n_[用户中断]_', citations, usedKb, true, stepsByMessageId[aiMessageId] || null);
        } else {
            console.error('发送消息失败:', err);
            updateAIMessage(aiMessageId, '抱歉，请求失败，请稍后重试。', [], false, true, stepsByMessageId[aiMessageId] || null);
        }
    } finally {
        isGenerating = false;
        abortController = null;
        updateInputState();
        // 刷新对话列表（更新标题等）
        loadChats();
    }
}

// 创建AI消息占位符
function createAIMessagePlaceholder(messageId) {
    const container = document.getElementById('chat-messages');
    if (!container) return null;
    
    // 移除欢迎消息
    const welcome = container.querySelector('.welcome-message');
    if (welcome) welcome.remove();
    
    const messageEl = document.createElement('div');
    messageEl.id = messageId;
    messageEl.className = 'message assistant streaming';
    messageEl.innerHTML = `
        <div class="message-content">
            <span class="typing-indicator">●</span>
        </div>
    `;
    
    container.appendChild(messageEl);
    container.scrollTop = container.scrollHeight;
    
    return messageEl;
}

// 更新AI消息内容
function updateAIMessage(messageId, content, citations, usedKb, isDone = false, steps = null) {
    const messageEl = document.getElementById(messageId);
    if (!messageEl) return;
    
    // 处理Markdown和换行
    let formattedContent = escapeHtml(content);
    formattedContent = formattedContent.replace(/\n/g, '<br>');
    
    // 添加知识库标记
    if (isDone && usedKb) {
        formattedContent += '<br><br><span class="kb-badge">📚 基于知识库回答</span>';
    }
    
    // 添加引用
    if (isDone && citations && citations.length > 0) {
        formattedContent += '<div class="citations">';
        formattedContent += '<div class="citations-title">📖 引用来源</div>';
        citations.forEach(cite => {
            formattedContent += `<div class="citation-item">${escapeHtml(cite.source)} 第${cite.page}页</div>`;
        });
        formattedContent += '</div>';
    }
    
    const stepsHtml = steps ? renderStepsHTML(steps) : '';
    const contentEl = messageEl.querySelector('.message-content');
    if (contentEl) {
        contentEl.innerHTML = formattedContent + stepsHtml;
    }
    
    if (isDone) {
        messageEl.classList.remove('streaming');
    }
    
    // 滚动到底部
    const container = document.getElementById('chat-messages');
    if (container) {
        container.scrollTop = container.scrollHeight;
    }
}

// 添加消息到UI（非流式）
function addMessageToUI(content, role, scroll = true, steps = []) {
    const container = document.getElementById('chat-messages');
    if (!container) return;
    
    // 移除欢迎消息
    const welcome = container.querySelector('.welcome-message');
    if (welcome) welcome.remove();
    
    const messageEl = document.createElement('div');
    messageEl.className = `message ${role}`;
    
    // 处理Markdown和换行
    let formattedContent = escapeHtml(content);
    formattedContent = formattedContent.replace(/\n/g, '<br>');
    
    const stepsHtml = steps && steps.length ? renderStepsHTML(steps) : '';
    messageEl.innerHTML = `<div class="message-content">${formattedContent}${stepsHtml}</div>`;
    
    container.appendChild(messageEl);
    
    if (scroll) {
        container.scrollTop = container.scrollHeight;
    }
}

// 添加消息到聊天（兼容旧代码）
function addMessage(content, role) {
    addMessageToUI(content, role, true);
}

// ==================== 变更提案 ====================

function showProposal(proposal) {
    const panel = document.getElementById('proposal-panel');
    if (!panel) return;
    
    document.getElementById('proposal-filename').textContent = proposal.filename;
    document.getElementById('proposal-action').textContent = proposal.action;
    document.getElementById('proposal-action').className = `action-tag ${proposal.action.toLowerCase()}`;
    document.getElementById('proposal-diff').textContent = proposal.diff;
    
    panel.classList.remove('hidden');
}

function hideProposal() {
    document.getElementById('proposal-panel')?.classList.add('hidden');
}

function applyProposal() {
    console.log('应用提案');
    hideProposal();
}

function rejectProposal() {
    hideProposal();
}

// 监听 Enter 键发送消息
document.addEventListener('keydown', (e) => {
    if (e.target.id === 'chat-input' && e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (!isGenerating) {
            sendMessage();
        }
    }
});

// 导出全局函数
window.selectFile = selectFile;
window.renderFilePreview = renderFilePreview;
window.renderMarkdown = renderMarkdown;
window.escapeHtml = escapeHtml;
window.startEditFile = startEditFile;
window.saveCurrentFile = saveCurrentFile;
window.cancelEditFile = cancelEditFile;
window.uploadFiles = uploadFiles;
window.uploadKBFiles = uploadKBFiles;
window.showUploadModal = showUploadModal;
window.hideUploadModal = hideUploadModal;
window.showKBUploadModal = showKBUploadModal;
window.hideKBUploadModal = hideKBUploadModal;
window.confirmDeleteFile = confirmDeleteFile;
window.deleteFile = deleteFile;
window.deleteKBFile = deleteKBFile;
window.refreshFiles = refreshFiles;
window.loadKBFiles = loadKBFiles;
window.createNewChat = createNewChat;
window.selectChat = selectChat;
window.confirmDeleteChat = confirmDeleteChat;
window.deleteChat = deleteChat;
window.showFileSelector = showFileSelector;
window.clearChat = clearChat;
window.sendMessage = sendMessage;
window.stopGeneration = stopGeneration;
window.showProposal = showProposal;
window.hideProposal = hideProposal;
window.applyProposal = applyProposal;
window.rejectProposal = rejectProposal;
