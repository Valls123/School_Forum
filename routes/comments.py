from flask import Blueprint, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from models import db, Comment, CommentVote

comments_bp = Blueprint('comments', __name__)


@comments_bp.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id):
    content = request.form.get('content', '').strip()
    if not content:
        flash('Комментарий не может быть пустым', 'error')
        return redirect(url_for('posts.post_detail', post_id=post_id))
    if len(content) > 1000:
        flash('Слишком длинный комментарий', 'error')
        return redirect(url_for('posts.post_detail', post_id=post_id))

    comment = Comment(content=content, author_id=current_user.id, post_id=post_id)
    db.session.add(comment)
    db.session.commit()
    return redirect(url_for('posts.post_detail', post_id=post_id) + '#comments')


@comments_bp.route('/comment/<int:comment_id>/vote/<int:value>')
@login_required
def vote_comment(comment_id, value):
    if value not in (1, -1):
        abort(400)
    comment = db.session.get(Comment, comment_id)
    if not comment:
        abort(404)

    existing = CommentVote.query.filter_by(
        user_id=current_user.id, comment_id=comment_id).first()

    if existing:
        if existing.value == value:
            comment.rating -= value
            db.session.delete(existing)
        else:
            comment.rating -= existing.value
            comment.rating += value
            existing.value = value
    else:
        comment.rating += value
        db.session.add(CommentVote(user_id=current_user.id,
                                   comment_id=comment_id, value=value))

    db.session.commit()
    return redirect(url_for('posts.post_detail', post_id=comment.post_id) + '#comments')


@comments_bp.route('/comment/<int:comment_id>/pin')
@login_required
def pin_comment(comment_id):
    comment = db.session.get(Comment, comment_id)
    if not comment:
        abort(404)
    if current_user.role not in ['Администратор', 'Модератор'] and \
            current_user.id != comment.post.author_id:
        abort(403)
    comment.is_pinned = not comment.is_pinned
    db.session.commit()
    return redirect(url_for('posts.post_detail', post_id=comment.post_id) + '#comments')


@comments_bp.route('/comment/<int:comment_id>/delete')
@login_required
def delete_comment(comment_id):
    comment = db.session.get(Comment, comment_id)
    if not comment:
        abort(404)
    if current_user.id != comment.author_id and \
            current_user.role not in ['Администратор', 'Модератор']:
        abort(403)

    CommentVote.query.filter_by(comment_id=comment_id).delete()
    db.session.delete(comment)
    db.session.commit()
    return redirect(url_for('posts.post_detail', post_id=comment.post_id) + '#comments')