from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from models import db, News, NewsVote

news_bp = Blueprint('news', __name__)


@news_bp.route('/news')
def news():
    items = News.query.order_by(News.date_posted.desc()).all()
    user_votes = {}
    if current_user.is_authenticated:
        for vote in NewsVote.query.filter_by(user_id=current_user.id).all():
            user_votes[vote.news_id] = vote.value
    return render_template('news.html', items=items, user_votes=user_votes)


@news_bp.route('/news/create', methods=['POST'])
@login_required
def create_news():
    if current_user.role != 'Администратор':
        abort(403)
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    if not title or not content:
        flash('Заполни все поля', 'error')
        return redirect(url_for('news.news'))
    item = News(title=title, content=content, author_id=current_user.id)
    db.session.add(item)
    db.session.commit()
    return redirect(url_for('news.news'))


@news_bp.route('/news/<int:news_id>/vote/<string:direction>')
@login_required
def vote_news(news_id, direction):
    value = 1 if direction == 'up' else -1
    item = db.session.get(News, news_id)
    if not item:
        abort(404)

    existing = NewsVote.query.filter_by(
        user_id=current_user.id, news_id=news_id).first()

    if existing:
        if existing.value == value:
            item.rating -= value
            db.session.delete(existing)
        else:
            item.rating -= existing.value
            item.rating += value
            existing.value = value
    else:
        item.rating += value
        db.session.add(NewsVote(user_id=current_user.id, news_id=news_id, value=value))

    db.session.commit()
    return redirect(url_for('news.news'))


@news_bp.route('/news/<int:news_id>/delete')
@login_required
def delete_news(news_id):
    if current_user.role != 'Администратор':
        abort(403)
    item = db.session.get(News, news_id)
    if not item:
        abort(404)
    NewsVote.query.filter_by(news_id=news_id).delete()
    db.session.delete(item)
    db.session.commit()
    flash('Новость удалена', 'success')
    return redirect(url_for('news.news'))
