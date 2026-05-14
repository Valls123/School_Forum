from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload
from models import db, Message
from extensions import socketio

chat_bp = Blueprint('chat', __name__)


@chat_bp.route('/secret_chat')
@login_required
def secret_chat():
    if not (current_user.is_cheater or current_user.role == 'Администратор'):
        abort(403)
    msgs = Message.query.options(joinedload(Message.user)) \
        .filter_by(is_deleted=False) \
        .order_by(Message.timestamp.desc()).limit(50).all()
    messages = list(reversed(msgs))
    return render_template('chat.html', messages=messages)


@chat_bp.route('/pin_message/<int:mid>')
@login_required
def pin_message(mid):
    if current_user.role != 'Администратор':
        abort(403)
    msg = db.session.get(Message, mid)
    if not msg:
        abort(404)
    if msg.is_pinned:
        msg.is_pinned = False
    else:
        Message.query.update({Message.is_pinned: False})
        msg.is_pinned = True
    db.session.commit()
    socketio.emit('reload_chat')
    return redirect(url_for('chat.secret_chat'))


def register_socket_handlers(socketio_instance):
    @socketio_instance.on('message')
    def handle_msg(data):
        from flask import session
        from models import User

        user_id = session.get('_user_id')
        if not user_id:
            return

        user = db.session.get(User, int(user_id))  # убрана лишняя строка выше

        if not user or not (user.is_cheater or user.role == 'Администратор'):
            return
        if user.banned_until and user.banned_until > datetime.now(timezone.utc):
            return

        try:
            msg = Message(content=data, user_id=user.id)
            db.session.add(msg)
            db.session.commit()

            saved = Message.query.options(joinedload(Message.user)).filter_by(id=msg.id).first()
            if saved and saved.user:
                socketio_instance.emit('message', {
                    'user_id': saved.user.id,
                    'username': saved.user.username,
                    'avatar': saved.user.avatar or 'default.png',
                    'msg': saved.content,
                    'timestamp': saved.timestamp.strftime('%H:%M')
                }, namespace='/')
        except Exception as e:
            print('Ошибка при сохранении сообщения:', e)
            db.session.rollback()


@chat_bp.route('/delete_message/<int:msg_id>')
@login_required
def delete_message(msg_id):
    msg = db.session.get(Message, msg_id)
    if not msg:
        abort(404)
    if current_user.role not in ['Администратор', 'Модератор']:
        abort(403)
    msg.is_deleted = True
    msg.deleted_by_id = current_user.id
    db.session.commit()
    socketio.emit('reload_chat', namespace='/')
    flash('Сообщение удалено', 'success')
    return redirect(request.referrer or url_for('chat.secret_chat'))
