import re
import time
from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, current_app
from flask_login import login_required, current_user
from sqlalchemy import func
from models import db, Post, Vote, Comment, CommentVote, User, Follow

posts_bp = Blueprint('posts', __name__)


def get_top_users():
    """Топ-5 пользователей по рейтингу с кешем на 5 минут."""
    cache = current_app.config.get('_top_users_cache')
    now = time.time()
    if not cache or now - cache['time'] > 300:
        rows = db.session.query(
            User.id,
            func.coalesce(func.sum(Vote.value), 0).label('total_rating')
        ).outerjoin(Post, Post.author_id == User.id) \
            .outerjoin(Vote, Vote.post_id == Post.id) \
            .filter(User.is_deleted == False) \
            .group_by(User.id) \
            .order_by(func.coalesce(func.sum(Vote.value), 0).desc()) \
            .limit(5).all()

        top_ids = [r.id for r in rows]
        users_map = {u.id: u for u in User.query.filter(User.id.in_(top_ids)).all()}
        top_users = [users_map[r.id] for r in rows if r.id in users_map]

        current_app.config['_top_users_cache'] = {'time': now, 'data': top_users}
    else:
        top_users = cache['data']
    return top_users


@posts_bp.route('/')
def index():
    sort = request.args.get('sort', 'new')
    page = request.args.get('page', 1, type=int)
    per_page = 15

    if sort == 'top':
        all_posts = Post.query.filter_by(hidden=False).all()
        all_posts = [p for p in all_posts if p.rating > 0]
        all_posts.sort(key=lambda p: p.rating, reverse=True)
        total = len(all_posts)
        posts = all_posts[(page - 1) * per_page: page * per_page]
    else:
        pagination = Post.query.filter_by(hidden=False) \
            .order_by(Post.date_posted.desc()) \
            .paginate(page=page, per_page=per_page, error_out=False)
        posts = pagination.items
        total = pagination.total

    has_more = (page * per_page) < total
    top_users = get_top_users() if page == 1 else []

    user_votes = {}
    if current_user.is_authenticated:
        for post in posts:
            user_votes[post.id] = post.user_vote(current_user)

    return render_template('index.html', posts=posts, user_votes=user_votes,
                           sort=sort, page=page, has_more=has_more,
                           top_users=top_users)


@posts_bp.route('/create_post', methods=['POST'])
@login_required
def create_post():
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    content = re.sub(r'\n{3,}', '\n\n', content)
    post = Post(title=title, content=content, author_id=current_user.id)
    db.session.add(post)
    db.session.commit()
    return redirect(url_for('posts.index'))


@posts_bp.route('/post/<int:post_id>')
def post_detail(post_id):
    post = db.session.get(Post, post_id)
    if not post:
        abort(404)

    comments = Comment.query.filter_by(post_id=post_id) \
        .order_by(Comment.is_pinned.desc(), Comment.date_posted.asc()).all()

    user_vote = 0
    comment_votes = {}
    if current_user.is_authenticated:
        v = Vote.query.filter_by(user_id=current_user.id, post_id=post_id).first()
        user_vote = v.value if v else 0
        for cv in CommentVote.query.filter_by(user_id=current_user.id).all():
            comment_votes[cv.comment_id] = cv.value

    return render_template('post.html', post=post, comments=comments,
                           user_vote=user_vote, comment_votes=comment_votes)


@posts_bp.route('/vote/<int:id>/<action>')
@login_required
def vote(id, action):
    post = db.session.get(Post, id)
    if not post:
        return redirect(request.referrer or url_for('posts.index'))

    value = 1 if action == 'up' else -1
    existing_vote = Vote.query.filter_by(user_id=current_user.id, post_id=id).first()

    if existing_vote:
        if existing_vote.value == value:
            db.session.delete(existing_vote)
        else:
            existing_vote.value = value
    else:
        db.session.add(Vote(user_id=current_user.id, post_id=id, value=value))

    db.session.commit()
    # Сбрасываем кеш топа при голосовании
    current_app.config.pop('_top_users_cache', None)
    return redirect(request.referrer or url_for('posts.index'))


@posts_bp.route('/following')
@login_required
def following_feed():
    page = request.args.get('page', 1, type=int)
    per_page = 15

    followed_ids = [f.followed_id for f in Follow.query.filter_by(
        follower_id=current_user.id).all()]

    if not followed_ids:
        return render_template('index.html', posts=[], user_votes={},
                               sort='following', page=1, has_more=False,
                               top_users=[], is_following_feed=True)

    pagination = Post.query \
        .filter(Post.author_id.in_(followed_ids), Post.hidden == False) \
        .order_by(Post.date_posted.desc()) \
        .paginate(page=page, per_page=per_page, error_out=False)

    posts = pagination.items
    has_more = (page * per_page) < pagination.total

    user_votes = {}
    for post in posts:
        user_votes[post.id] = post.user_vote(current_user)

    return render_template('index.html', posts=posts, user_votes=user_votes,
                           sort='following', page=page, has_more=has_more,
                           top_users=[], is_following_feed=True)


@posts_bp.route('/hide_post/<int:post_id>')
@login_required
def hide_post(post_id):
    post = db.session.get(Post, post_id)
    if not post:
        abort(404)
    if current_user.role not in ['Администратор', 'Модератор']:
        abort(403)
    post.hidden = True
    post.hidden_by_id = current_user.id
    post.hidden_at = datetime.now(timezone.utc)
    db.session.commit()
    flash('Пост скрыт на модерацию', 'success')
    return redirect(request.referrer or url_for('posts.index'))


@posts_bp.route('/moderation/posts')
@login_required
def moderation_posts():
    if current_user.role != 'Администратор':
        abort(403)
    hidden_posts = Post.query.filter_by(hidden=True).order_by(Post.hidden_at.desc()).all()
    return render_template('moderation_posts.html', posts=hidden_posts)


@posts_bp.route('/moderate_post/<int:post_id>/<action>')
@login_required
def moderate_post(post_id, action):
    if current_user.role != 'Администратор':
        abort(403)
    post = db.session.get(Post, post_id)
    if not post:
        abort(404)

    if action == 'restore':
        post.hidden = False
        post.hidden_by_id = None
        post.hidden_at = None
        flash('Пост восстановлен', 'success')
    elif action == 'delete':
        Vote.query.filter_by(post_id=post.id).delete()
        db.session.delete(post)
        flash('Пост удалён навсегда', 'success')
    else:
        abort(400)

    db.session.commit()
    return redirect(url_for('posts.moderation_posts'))


@posts_bp.route('/api/posts')
def posts_api():
    sort = request.args.get('sort', 'new')
    page = request.args.get('page', 1, type=int)
    per_page = 15

    if sort == 'following':
        if not current_user.is_authenticated:
            return {'posts': [], 'has_more': False}
        followed_ids = [f.followed_id for f in Follow.query.filter_by(
            follower_id=current_user.id).all()]
        if not followed_ids:
            return {'posts': [], 'has_more': False}
        pagination = Post.query \
            .filter(Post.author_id.in_(followed_ids), Post.hidden == False) \
            .order_by(Post.date_posted.desc()) \
            .paginate(page=page, per_page=per_page, error_out=False)
        posts = pagination.items
        total = pagination.total
    elif sort == 'top':
        all_posts = Post.query.filter_by(hidden=False).all()
        all_posts = [p for p in all_posts if p.rating > 0]
        all_posts.sort(key=lambda p: p.rating, reverse=True)
        total = len(all_posts)
        posts = all_posts[(page - 1) * per_page: page * per_page]
    else:
        pagination = Post.query.filter_by(hidden=False) \
            .order_by(Post.date_posted.desc()) \
            .paginate(page=page, per_page=per_page, error_out=False)
        posts = pagination.items
        total = pagination.total

    has_more = (page * per_page) < total

    user_votes = {}
    if current_user.is_authenticated:
        for post in posts:
            user_votes[post.id] = post.user_vote(current_user)

    posts_data = [{
        'id': p.id,
        'title': p.title,
        'content': p.content,
        'rating': p.rating,
        'user_vote': user_votes.get(p.id, 0),
        'date': p.date_posted.strftime('%d.%m.%Y %H:%M'),
        'author_id': p.author.id,
        'author_username': p.author.username,
        'author_avatar': p.author.avatar or 'default.png',
        'author_verified': p.author.is_verified,
        'author_role': p.author.role,
        'hidden': p.hidden,
    } for p in posts]

    return {'posts': posts_data, 'has_more': has_more}
