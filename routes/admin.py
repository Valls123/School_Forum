from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from models import db, User, Post, Vote

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.route('/')
@login_required
def admin():
    if current_user.role != 'Администратор':
        abort(403)
    users = User.query.all()
    hidden_count = Post.query.filter_by(hidden=True).count()
    now = datetime.now(timezone.utc)
    return render_template('admin.html', users=users, hidden_count=hidden_count, now=now)


@admin_bp.route('/toggle_role/<int:uid>', methods=['POST'])
@login_required
def toggle_role(uid):
    if current_user.role != 'Администратор':
        abort(403)

    u = db.session.get(User, uid)
    if not u:
        abort(404)
    if u.id == current_user.id:
        flash('Нельзя изменить свою собственную роль', 'danger')
        return redirect(url_for('admin.admin'))

    action = request.form.get('action')

    if action == 'make_admin':
        u.role = 'Администратор'
        u.is_cheater = True
        flash(f'{u.username} теперь администратор', 'success')
    elif action == 'remove_admin':
        u.role = 'Участник'
        flash(f'У {u.username} забраны права администратора', 'warning')
    elif action == 'make_moderator':
        u.role = 'Модератор'
        flash(f'{u.username} теперь модератор', 'success')
    elif action == 'remove_moderator':
        u.role = 'Участник'
        flash(f'У {u.username} забраны права модератора', 'warning')
    elif action == 'toggle_secret':
        u.is_cheater = not u.is_cheater
        status = 'предоставлен' if u.is_cheater else 'закрыт'
        flash(f'Доступ к секретному чату для {u.username} {status}', 'info')

    db.session.commit()
    return redirect(url_for('admin.admin'))


@admin_bp.route('/toggle_verify/<int:uid>', methods=['POST'])
@login_required
def toggle_verify(uid):
    if current_user.role != 'Администратор':
        abort(403)
    user = db.session.get(User, uid)
    if not user:
        abort(404)
    user.is_verified = not user.is_verified
    db.session.commit()
    flash(f'Статус верификации {user.username} изменён', 'success')
    return redirect(url_for('admin.admin'))


@admin_bp.route('/ban_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
def ban_user(user_id):
    if current_user.role != 'Администратор':
        abort(403)
    user = db.session.get(User, user_id)
    if not user:
        abort(404)

    if request.method == 'POST':
        duration = request.form.get('duration')
        if duration == 'permanent':
            user.banned_until = None
            user.is_banned_permanent = True
        else:
            minutes = int(duration)
            user.banned_until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
            user.is_banned_permanent = False
        db.session.commit()
        flash(f'Пользователь {user.username} заблокирован', 'success')
        return redirect(url_for('admin.admin'))

    return render_template('ban_user.html', user=user)


@admin_bp.route('/unban_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
def unban_user(user_id):
    if current_user.role != 'Администратор':
        abort(403)
    user = db.session.get(User, user_id)
    if not user:
        abort(404)

    if request.method == 'POST':
        user.banned_until = None
        user.is_banned_permanent = False
        db.session.commit()
        flash(f'Пользователь {user.username} разблокирован', 'success')
        return redirect(url_for('admin.admin'))

    return render_template('unban_user.html', user=user)


@admin_bp.route('/delete_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
def delete_user(user_id):
    if current_user.role != 'Администратор':
        abort(403)
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    if user.id == current_user.id:
        abort(403)

    if request.method == 'POST':
        username = user.username
        for post in user.posts:
            Vote.query.filter_by(post_id=post.id).delete()
        Vote.query.filter_by(user_id=user.id).delete()
        Post.query.filter_by(hidden_by_id=user.id).update({
            'hidden_by_id': None, 'hidden_at': None
        })
        Post.query.filter_by(author_id=user.id).delete()
        db.session.delete(user)
        db.session.commit()
        flash(f'Профиль {username} и все его посты удалены', 'success')
        return redirect(url_for('admin.admin'))

    return render_template('delete_user.html', user=user)


@admin_bp.route('/clan/<int:clan_id>/verify')
@login_required
def verify_clan(clan_id):
    if current_user.role != 'Администратор':
        abort(403)
    from models import Clan
    clan = db.session.get(Clan, clan_id)
    if clan:
        clan.is_verified = not clan.is_verified
        db.session.commit()
        flash(f'Верификация клана {clan.name} изменена', 'success')
    return redirect(url_for('admin.admin'))


@admin_bp.route('/clan/<int:clan_id>/delete', methods=['POST'])
@login_required
def delete_clan(clan_id):
    if current_user.role != 'Администратор':
        abort(403)
    from models import Clan, ClanPost, ClanPostVote, ClanMember, ClanInvite
    clan = db.session.get(Clan, clan_id)
    if clan:
        for post in clan.posts:
            ClanPostVote.query.filter_by(post_id=post.id).delete()
        db.session.delete(clan)
        db.session.commit()
        flash(f'Клан удалён', 'success')
    return redirect(url_for('admin.admin'))
