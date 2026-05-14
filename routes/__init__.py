from .auth import auth_bp
from .posts import posts_bp
from .comments import comments_bp
from .profile import profile_bp
from .admin import admin_bp
from .chat import chat_bp
from .api import api_bp
from .news import news_bp
from .clans import clans_bp


def register_blueprints(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(posts_bp)
    app.register_blueprint(comments_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(news_bp)
    app.register_blueprint(clans_bp)
