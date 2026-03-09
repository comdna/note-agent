from flask import Blueprint, render_template, send_from_directory

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    return render_template('index.html')

@bp.route('/project/<project_id>')
def project(project_id):
    return render_template('project.html', project_id=project_id)

@bp.route('/uploads/<path:filename>')
def uploaded_file(filename):
    from flask import current_app
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)
