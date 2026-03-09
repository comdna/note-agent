from flask import Flask
from flask_cors import CORS
import os

def create_app():
    # 获取项目根目录
    basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    app = Flask(__name__,
                template_folder=os.path.join(basedir, 'templates'),
                static_folder=os.path.join(basedir, 'static'))
    
    # 配置
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
    app.config['DATA_FOLDER'] = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max upload
    
    # 确保目录存在
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['DATA_FOLDER'], exist_ok=True)
    
    # 初始化服务的数据目录
    from app.services import project_service, file_service, kb_service, chat_service
    project_service.init_data_dir(app.config['DATA_FOLDER'])
    file_service.init_data_dir(app.config['DATA_FOLDER'], app.config['UPLOAD_FOLDER'])
    kb_service.init_data_dir(app.config['DATA_FOLDER'], app.config['UPLOAD_FOLDER'])
    chat_service.init_data_dir(app.config['DATA_FOLDER'])
    
    CORS(app)
    
    # 注册路由
    from app.routes import main, api
    app.register_blueprint(main.bp)
    app.register_blueprint(api.bp, url_prefix='/api')
    
    return app
