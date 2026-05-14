import os
from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import db, Clan, ClanMember, ClanInvite, ClanPost, ClanPostVote, User

clans_bp = Blueprint('clans', __name__, url_prefix='/clans')


def get_user_clan():
    if not current_user.is_authenticated:
        return None
    return current_user.clan_membership


def can_post_in_clan(clan):
    m = get_user_clan()
    if not m or m.clan_id != clan.id:
        return False
    return m.role in ['Глава', 'Страж']


# ─── Список кланов ────────────────────────────────────────────────────────────

@clans_bp.route('/')
def index():
    clans = Clan.query.all()
    clans.sort(key=lambda c: c.rating, reverse=True)
    return render_template('clans/index.html', clans=clans)


# ─── Создать клан ─────────────────────────────────────────────────────────────

@clans_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    if not current_user.is_verified:
        flash('Создавать кланы могут только верифицированные пользователи', 'error')
        return redirect(url_for('clans.index'))

    if current_user.clan_membership:
        flash('Вы уже состоите в клане', 'error')
        return redirect(url_for('clans.index'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        mode = request.form.get('mode', 'open')

        if not name:
            flash('Введите название клана', 'error')
            return redirect(url_for('clans.create'))

        if len(name) < 2 or len(name) > 50:
            flash('Название клана: 2–50 символов', 'error')
            return redirect(url_for('clans.create'))

        if Clan.query.filter_by(name=name).first():
            flash('Клан с таким названием уже существует', 'error')
            return redirect(url_for('clans.create'))

        clan = Clan(name=name, description=description, mode=mode, owner_id=current_user.id)
        db.session.add(clan)
        db.session.flush()

        # Автоматически добавляем создателя как Главу
        member = ClanMember(user_id=current_user.id, clan_id=clan.id, role='Глава')
        db.session.add(member)

        # Загрузка аватара
        avatar = request.files.get('avatar')
        if avatar and avatar.filename:
            filename = secure_filename(f"clan_avatar_{clan.id}.png")
            avatar.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
            clan.avatar = filename

        # Загрузка баннера
        banner = request.files.get('banner')
        if banner and banner.filename:
            filename = secure_filename(f"clan_banner_{clan.id}.png")
            banner.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
            clan.banner = filename

        db.session.commit()
        flash(f'Клан «{clan.name}» создан!', 'success')
        return redirect(url_for('clans.view', clan_id=clan.id))

    return render_template('clans/create.html')


# ─── Страница клана ───────────────────────────────────────────────────────────

@clans_bp.route('/<int:clan_id>')
def view(clan_id):
    clan = db.session.get(Clan, clan_id)
    if not clan:
        abort(404)

    membership = current_user.clan_membership if current_user.is_authenticated else None
    user_in_clan = membership and membership.clan_id == clan_id
    user_role = membership.role if user_in_clan else None

    # Заявки/приглашения текущего пользователя
    user_invite = None
    if current_user.is_authenticated and not user_in_clan:
        user_invite = ClanInvite.query.filter_by(
            clan_id=clan_id, user_id=current_user.id).first()

    user_votes = {}
    if current_user.is_authenticated:
        for post in clan.posts:
            user_votes[post.id] = post.user_vote(current_user)

    posts = sorted(clan.posts, key=lambda p: p.date_posted, reverse=True)
    members = ClanMember.query.filter_by(clan_id=clan_id).all()

    # Заявки на вступление (только для главы)
    requests = []
    if user_role == 'Глава':
        requests = ClanInvite.query.filter_by(clan_id=clan_id, type='request').all()

    return render_template('clans/view.html', clan=clan, posts=posts,
                           members=members, user_role=user_role,
                           user_in_clan=user_in_clan, user_invite=user_invite,
                           user_votes=user_votes, requests=requests)


# ─── Вступить / Подать заявку ─────────────────────────────────────────────────

@clans_bp.route('/<int:clan_id>/join')
@login_required
def join(clan_id):
    clan = db.session.get(Clan, clan_id)
    if not clan:
        abort(404)

    if current_user.clan_membership:
        flash('Вы уже состоите в клане', 'error')
        return redirect(url_for('clans.view', clan_id=clan_id))

    if clan.mode == 'closed':
        flash('Этот клан закрыт для вступления', 'error')
        return redirect(url_for('clans.view', clan_id=clan_id))

    if clan.mode == 'open':
        member = ClanMember(user_id=current_user.id, clan_id=clan_id, role='Участник')
        db.session.add(member)
        db.session.commit()
        flash(f'Вы вступили в клан «{clan.name}»', 'success')
    elif clan.mode == 'restricted':
        existing = ClanInvite.query.filter_by(
            clan_id=clan_id, user_id=current_user.id).first()
        if existing:
            flash('Заявка уже отправлена', 'info')
        else:
            invite = ClanInvite(clan_id=clan_id, user_id=current_user.id, type='request')
            db.session.add(invite)
            db.session.commit()
            flash('Заявка на вступление отправлена', 'success')

    return redirect(url_for('clans.view', clan_id=clan_id))


# ─── Принять/отклонить заявку ─────────────────────────────────────────────────

@clans_bp.route('/<int:clan_id>/request/<int:invite_id>/<action>')
@login_required
def handle_request(clan_id, invite_id, action):
    clan = db.session.get(Clan, clan_id)
    if not clan:
        abort(404)

    membership = current_user.clan_membership
    if not membership or membership.clan_id != clan_id or membership.role != 'Глава':
        abort(403)

    invite = db.session.get(ClanInvite, invite_id)
    if not invite or invite.clan_id != clan_id:
        abort(404)

    if action == 'accept':
        member = ClanMember(user_id=invite.user_id, clan_id=clan_id, role='Участник')
        db.session.add(member)
        db.session.delete(invite)
        db.session.commit()
        flash('Пользователь принят в клан', 'success')
    elif action == 'decline':
        db.session.delete(invite)
        db.session.commit()
        flash('Заявка отклонена', 'info')

    return redirect(url_for('clans.view', clan_id=clan_id))


# ─── Принять приглашение ──────────────────────────────────────────────────────

@clans_bp.route('/invite/<int:invite_id>/accept')
@login_required
def accept_invite(invite_id):
    invite = db.session.get(ClanInvite, invite_id)
    if not invite or invite.user_id != current_user.id or invite.type != 'invite':
        abort(404)

    if current_user.clan_membership:
        flash('Вы уже состоите в клане', 'error')
        db.session.delete(invite)
        db.session.commit()
        return redirect(url_for('clans.index'))

    member = ClanMember(user_id=current_user.id, clan_id=invite.clan_id, role='Участник')
    db.session.add(member)
    db.session.delete(invite)
    db.session.commit()
    flash('Вы приняли приглашение и вступили в клан', 'success')
    return redirect(url_for('clans.view', clan_id=invite.clan_id))


# ─── Пригласить пользователя ──────────────────────────────────────────────────

@clans_bp.route('/<int:clan_id>/invite/<int:user_id>')
@login_required
def invite_user(clan_id, user_id):
    clan = db.session.get(Clan, clan_id)
    if not clan:
        abort(404)

    membership = current_user.clan_membership
    if not membership or membership.clan_id != clan_id or membership.role not in ['Глава', 'Страж']:
        abort(403)

    target = db.session.get(User, user_id)
    if not target or target.clan_membership:
        flash('Пользователь уже состоит в клане или не найден', 'error')
        return redirect(url_for('clans.view', clan_id=clan_id))

    existing = ClanInvite.query.filter_by(clan_id=clan_id, user_id=user_id).first()
    if existing:
        flash('Приглашение уже отправлено', 'info')
    else:
        invite = ClanInvite(clan_id=clan_id, user_id=user_id, type='invite')
        db.session.add(invite)
        db.session.commit()
        flash(f'Приглашение отправлено {target.username}', 'success')

    return redirect(url_for('clans.view', clan_id=clan_id))


# ─── Выйти из клана ───────────────────────────────────────────────────────────

@clans_bp.route('/<int:clan_id>/leave')
@login_required
def leave(clan_id):
    membership = current_user.clan_membership
    if not membership or membership.clan_id != clan_id:
        abort(404)

    if membership.role == 'Глава':
        flash('Глава не может покинуть клан. Передайте права или удалите клан.', 'error')
        return redirect(url_for('clans.view', clan_id=clan_id))

    db.session.delete(membership)
    db.session.commit()
    flash('Вы покинули клан', 'info')
    return redirect(url_for('clans.index'))


# ─── Кикнуть участника ────────────────────────────────────────────────────────

@clans_bp.route('/<int:clan_id>/kick/<int:user_id>')
@login_required
def kick(clan_id, user_id):
    clan = db.session.get(Clan, clan_id)
    if not clan:
        abort(404)

    my = current_user.clan_membership
    is_admin = current_user.role == 'Администратор'
    is_leader = my and my.clan_id == clan_id and my.role == 'Глава'

    if not is_admin and not is_leader:
        abort(403)

    target = ClanMember.query.filter_by(clan_id=clan_id, user_id=user_id).first()
    if not target or target.role == 'Глава':
        flash('Нельзя кикнуть главу клана', 'error')
        return redirect(url_for('clans.view', clan_id=clan_id))

    db.session.delete(target)
    db.session.commit()
    flash('Участник исключён из клана', 'success')
    return redirect(url_for('clans.view', clan_id=clan_id))


# ─── Изменить роль участника ──────────────────────────────────────────────────

@clans_bp.route('/<int:clan_id>/role/<int:user_id>', methods=['POST'])
@login_required
def set_role(clan_id, user_id):
    my = current_user.clan_membership
    if not my or my.clan_id != clan_id or my.role != 'Глава':
        abort(403)

    if user_id == current_user.id:
        flash('Нельзя изменить свою роль', 'error')
        return redirect(url_for('clans.view', clan_id=clan_id))

    target = ClanMember.query.filter_by(clan_id=clan_id, user_id=user_id).first()
    if not target:
        abort(404)

    new_role = request.form.get('role')
    if new_role not in ['Страж', 'Участник']:
        flash('Недопустимая роль', 'error')
        return redirect(url_for('clans.view', clan_id=clan_id))

    target.role = new_role
    db.session.commit()
    flash(f'Роль участника изменена на {new_role}', 'success')
    return redirect(url_for('clans.view', clan_id=clan_id))


# ─── Настройки клана ─────────────────────────────────────────────────────────

@clans_bp.route('/<int:clan_id>/settings', methods=['GET', 'POST'])
@login_required
def settings(clan_id):
    clan = db.session.get(Clan, clan_id)
    if not clan:
        abort(404)

    my = current_user.clan_membership
    if not my or my.clan_id != clan_id or my.role != 'Глава':
        abort(403)

    if request.method == 'POST':
        description = request.form.get('description', '').strip()
        mode = request.form.get('mode', 'open')

        if mode not in ['open', 'restricted', 'closed']:
            flash('Недопустимый режим', 'error')
            return redirect(url_for('clans.settings', clan_id=clan_id))

        clan.description = description
        clan.mode = mode

        avatar = request.files.get('avatar')
        if avatar and avatar.filename:
            filename = secure_filename(f"clan_avatar_{clan.id}.png")
            avatar.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
            clan.avatar = filename

        banner = request.files.get('banner')
        if banner and banner.filename:
            filename = secure_filename(f"clan_banner_{clan.id}.png")
            banner.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
            clan.banner = filename

        db.session.commit()
        flash('Настройки клана сохранены', 'success')
        return redirect(url_for('clans.view', clan_id=clan_id))

    return render_template('clans/settings.html', clan=clan)


# ─── Пост от клана ───────────────────────────────────────────────────────────

@clans_bp.route('/<int:clan_id>/post', methods=['POST'])
@login_required
def create_post(clan_id):
    clan = db.session.get(Clan, clan_id)
    if not clan:
        abort(404)

    if not can_post_in_clan(clan):
        abort(403)

    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()

    if not title or not content:
        flash('Заполни все поля', 'error')
        return redirect(url_for('clans.view', clan_id=clan_id))

    post = ClanPost(clan_id=clan_id, author_id=current_user.id,
                    title=title, content=content)
    db.session.add(post)
    db.session.commit()
    return redirect(url_for('clans.view', clan_id=clan_id))


# ─── Удалить пост клана ───────────────────────────────────────────────────────

@clans_bp.route('/<int:clan_id>/post/<int:post_id>/delete')
@login_required
def delete_post(clan_id, post_id):
    clan = db.session.get(Clan, clan_id)
    post = db.session.get(ClanPost, post_id)
    if not clan or not post or post.clan_id != clan_id:
        abort(404)

    my = current_user.clan_membership
    is_admin = current_user.role == 'Администратор'
    is_leader = my and my.clan_id == clan_id and my.role == 'Глава'

    if not is_admin and not is_leader:
        abort(403)

    ClanPostVote.query.filter_by(post_id=post_id).delete()
    db.session.delete(post)
    db.session.commit()
    flash('Пост удалён', 'success')
    return redirect(url_for('clans.view', clan_id=clan_id))


# ─── Голосование за пост клана ────────────────────────────────────────────────

@clans_bp.route('/<int:clan_id>/post/<int:post_id>/vote/<string:direction>')
@login_required
def vote_post(clan_id, post_id, direction):
    post = db.session.get(ClanPost, post_id)
    if not post or post.clan_id != clan_id:
        abort(404)

    value = 1 if direction == 'up' else -1
    existing = ClanPostVote.query.filter_by(
        user_id=current_user.id, post_id=post_id).first()

    if existing:
        if existing.value == value:
            db.session.delete(existing)
        else:
            existing.value = value
    else:
        db.session.add(ClanPostVote(user_id=current_user.id, post_id=post_id, value=value))

    db.session.commit()
    return redirect(url_for('clans.view', clan_id=clan_id))


@clans_bp.route('/<int:clan_id>/verify')
@login_required
def verify_clan(clan_id):
    if current_user.role not in ['Администратор', 'Модератор']:
        abort(403)
    clan = db.session.get(Clan, clan_id)
    if not clan:
        abort(404)
    clan.is_verified = not clan.is_verified
    db.session.commit()
    flash(f'Верификация клана «{clan.name}» {"выдана" if clan.is_verified else "снята"}', 'success')
    return redirect(url_for('clans.view', clan_id=clan_id))
