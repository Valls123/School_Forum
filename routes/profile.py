import os
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import db, User, Follow

profile_bp = Blueprint('profile', __name__)


@profile_bp.route('/profile/<int:id>')
def profile(id):
    user = db.session.get(User, id)
    if not user:
        abort(404)

    if current_user.is_authenticated and current_user.role in ['Администратор', 'Модератор']:
        posts = user.posts
    else:
        posts = [p for p in user.posts if not p.hidden]

    # Место в топе
    from models import User as U
    all_users = U.query.filter_by(is_deleted=False).all()
    all_users.sort(key=lambda u: u.rating, reverse=True)  # только нужные поля
    top_rank = None
    for i, u in enumerate(all_users, 1):
        if u.id == user.id:
            top_rank = i
            break

    return render_template('profile.html', user=user, posts=posts, top_rank=top_rank)


@profile_bp.route('/edit_profile', methods=['POST'])
@login_required
def edit_profile():
    new_bio = request.form.get('bio')
    if new_bio and new_bio.strip():
        current_user.bio = new_bio

    file = request.files.get('avatar')
    if file and file.filename != '':
        filename = secure_filename(f"user_{current_user.id}.png")
        file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
        current_user.avatar = filename

    banner = request.files.get('banner')
    if banner and banner.filename != '':
        banner_filename = secure_filename(f"banner_{current_user.id}.png")
        banner.save(os.path.join(current_app.config['UPLOAD_FOLDER'], banner_filename))
        current_user.banner = banner_filename

    db.session.commit()
    return redirect(url_for('profile.profile', id=current_user.id))


@profile_bp.route('/follow/<int:user_id>')
@login_required
def follow(user_id):
    if user_id == current_user.id:
        flash('Нельзя подписаться на самого себя', 'warning')
        return redirect(url_for('profile.profile', id=user_id))

    user = db.session.get(User, user_id)
    if not user:
        abort(404)

    existing = Follow.query.filter_by(
        follower_id=current_user.id, followed_id=user_id).first()

    if existing:
        flash(f'Вы уже подписаны на {user.username}', 'info')
    else:
        db.session.add(Follow(follower_id=current_user.id, followed_id=user_id))
        db.session.commit()
        flash(f'Вы подписались на {user.username}', 'success')

    return redirect(url_for('profile.profile', id=user_id))


@profile_bp.route('/unfollow/<int:user_id>')
@login_required
def unfollow(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)

    follow = Follow.query.filter_by(
        follower_id=current_user.id, followed_id=user_id).first()

    if follow:
        db.session.delete(follow)
        db.session.commit()
        flash(f'Вы отписались от {user.username}', 'success')
    else:
        flash(f'Вы не были подписаны на {user.username}', 'info')

    return redirect(url_for('profile.profile', id=user_id))


@profile_bp.route('/followers/<int:user_id>')
def followers(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    followers_list = [f.follower for f in user.followers]
    return render_template('followers.html', user=user, users=followers_list, title='Подписчики')


@profile_bp.route('/following/<int:user_id>')
def following(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    following_list = [f.followed for f in user.following]
    return render_template('followers.html', user=user, users=following_list, title='Подписки')
