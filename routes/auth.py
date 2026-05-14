import re
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password')

        if not username:
            flash('Ник не может быть пустым', 'error')
            return redirect(url_for('auth.register'))

        if len(username) < 3 or len(username) > 20:
            flash('Ник должен быть от 3 до 20 символов', 'error')
            return redirect(url_for('auth.register'))

        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', username):
            flash('Ник должен начинаться с буквы, содержать только латиницу, цифры и _', 'error')
            return redirect(url_for('auth.register'))

        if User.query.filter_by(username=username).first():
            flash('Этот ник уже занят!', 'error')
            return redirect(url_for('auth.register'))

        role = 'Администратор' if User.query.count() == 0 else 'Участник'
        hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, password_hash=hashed_pw, role=role)
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('posts.index'))

    return render_template('register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if not user:
            flash('Аккаунт с таким ником не найден', 'error')
        elif not check_password_hash(user.password_hash, password):
            flash('Неверный пароль', 'error')
        else:
            login_user(user, remember=True)
            return redirect(url_for('posts.index'))

    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('posts.index'))