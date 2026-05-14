import os
import eventlet

eventlet.monkey_patch()

from datetime import datetime, timezone
from flask import Flask, redirect, url_for, flash
from flask_login import current_user, logout_user
from sqlalchemy import event

from extensions import db, login_manager, socketio
from models import User
from utils import datetimeformat
from routes import register_blueprints
from routes.chat import register_socket_handlers


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'dev-key-123'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///forum.db'
    app.config['UPLOAD_FOLDER'] = os.path.join('static', 'avatars')

    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])

    # Инициализация расширений
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    socketio.init_app(app, async_mode='eventlet')

    # Фильтр шаблонов
    app.template_filter('datetimeformat')(datetimeformat)

    # Регистрация blueprints
    register_blueprints(app)

    # Регистрация socket handlers
    register_socket_handlers(socketio)

    # SQLAlchemy event  aware datetime
    @event.listens_for(User, 'load')
    def receive_load(target, context):
        for attr in ('banned_until', 'reg_date', 'last_seen'):
            val = getattr(target, attr, None)
            if val is not None and val.tzinfo is None:
                setattr(target, attr, val.replace(tzinfo=timezone.utc))

    # Обработчики ошибок
    @app.errorhandler(403)
    def forbidden(e):
        from flask import render_template
        return render_template('403.html'), 403

    @app.errorhandler(404)
    def not_found(e):
        from flask import render_template
        return render_template('404.html'), 404

    # Before request хуки
    @app.before_request
    def update_last_seen():
        if current_user.is_authenticated:
            current_user.last_seen = datetime.now(timezone.utc)
            db.session.commit()

    @app.before_request
    def check_ban():
        if not current_user.is_authenticated:
            return
        from flask import request
        if request.endpoint in ('static', 'auth.login', 'auth.logout'):
            return

        if current_user.is_deleted:
            logout_user()
            flash('Ваш профиль был удалён администрацией.', 'danger')
            return redirect(url_for('auth.login'))

        banned_until = current_user.banned_until
        if banned_until and banned_until.tzinfo is None:
            banned_until = banned_until.replace(tzinfo=timezone.utc)

        if current_user.is_banned_permanent or \
                (banned_until and banned_until > datetime.now(timezone.utc)):
            logout_user()
            msg = 'Ваш профиль заблокирован навсегда' if current_user.is_banned_permanent \
                else f'Ваш профиль заблокирован до {banned_until.strftime("%d.%m.%Y %H:%M")} UTC'
            flash(msg, 'danger')
            return redirect(url_for('auth.login'))

    return app


@login_manager.user_loader
def load_user(uid):
    return db.session.get(User, int(uid))


app = create_app()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True)
