from extensions import db
from flask_login import UserMixin
from datetime import datetime, timezone


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), default='Участник')
    is_cheater = db.Column(db.Boolean, default=False)
    bio = db.Column(db.String(200), default="No bio")
    avatar = db.Column(db.String(200), default="default.png")
    reg_date = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    is_verified = db.Column(db.Boolean, default=False)
    banned_until = db.Column(db.DateTime(timezone=True), nullable=True)
    is_deleted = db.Column(db.Boolean, default=False)
    is_banned_permanent = db.Column(db.Boolean, default=False)
    banner = db.Column(db.String(200), default="default_banner.png")

    posts = db.relationship(
        'Post',
        foreign_keys='Post.author_id',
        back_populates='author',
        lazy=True,
        cascade="all, delete-orphan"
    )
    hidden_posts = db.relationship(
        'Post',
        foreign_keys='Post.hidden_by_id',
        back_populates='hidden_by',
        lazy=True
    )
    messages = db.relationship(
        'Message',
        foreign_keys='Message.user_id',
        back_populates='user',
        lazy=True
    )
    deleted_messages = db.relationship(
        'Message',
        foreign_keys='Message.deleted_by_id',
        back_populates='deleted_by',
        lazy=True
    )
    followers = db.relationship(
        'Follow',
        foreign_keys='Follow.followed_id',
        backref='followed',
        lazy='dynamic',
        cascade="all, delete-orphan"
    )
    following = db.relationship(
        'Follow',
        foreign_keys='Follow.follower_id',
        backref='follower',
        lazy='dynamic',
        cascade="all, delete-orphan"
    )

    def is_online(self):
        if not self.last_seen:
            return False
        diff = datetime.now(timezone.utc) - self.last_seen.replace(tzinfo=timezone.utc)
        return diff.total_seconds() < 300

    @property
    def rating(self):
        from sqlalchemy import func
        result = db.session.query(func.coalesce(func.sum(Vote.value), 0))\
            .join(Post, Post.id == Vote.post_id)\
            .filter(Post.author_id == self.id)\
            .scalar()
        return result or 0

    @property
    def followers_count(self):
        return Follow.query.filter_by(followed_id=self.id).count()

    @property
    def following_count(self):
        return Follow.query.filter_by(follower_id=self.id).count()

    def is_followed_by(self, user):
        if not user.is_authenticated:
            return False
        return self.followers.filter_by(follower_id=user.id).first() is not None


class Follow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    followed_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (db.UniqueConstraint('follower_id', 'followed_id', name='unique_follow'),)


class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    value = db.Column(db.Integer)

    user = db.relationship('User', backref='votes')
    post = db.relationship('Post', back_populates='vote_list')


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    is_pinned = db.Column(db.Boolean, default=False)
    rating = db.Column(db.Integer, default=0)

    author = db.relationship('User', foreign_keys=[author_id], backref='comments')
    post = db.relationship('Post', foreign_keys=[post_id], backref='comments')


class CommentVote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    comment_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=False)
    value = db.Column(db.Integer)

    user = db.relationship('User', backref='comment_votes')
    comment = db.relationship('Comment', backref='votes')


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    hidden = db.Column(db.Boolean, default=False)
    hidden_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    hidden_at = db.Column(db.DateTime, nullable=True)

    author = db.relationship('User', foreign_keys=[author_id], back_populates='posts')
    hidden_by = db.relationship('User', foreign_keys=[hidden_by_id], back_populates='hidden_posts')
    vote_list = db.relationship('Vote', back_populates='post', lazy='dynamic')

    @property
    def is_expired(self):
        diff = datetime.now(timezone.utc) - self.date_posted.replace(tzinfo=timezone.utc)
        return diff.total_seconds() > 86400

    @property
    def rating(self):
        return sum(vote.value for vote in self.vote_list)

    def user_vote(self, user):
        vote = Vote.query.filter_by(user_id=user.id, post_id=self.id).first()
        return vote.value if vote else 0


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_pinned = db.Column(db.Boolean, default=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    is_deleted = db.Column(db.Boolean, default=False)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    user = db.relationship('User', foreign_keys=[user_id], back_populates='messages')
    deleted_by = db.relationship('User', foreign_keys=[deleted_by_id], back_populates='deleted_messages')


class News(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    rating = db.Column(db.Integer, default=0)

    author = db.relationship('User', backref='news')


class NewsVote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    news_id = db.Column(db.Integer, db.ForeignKey('news.id'), nullable=False)
    value = db.Column(db.Integer)

    user = db.relationship('User', backref='news_votes')
    news = db.relationship('News', backref='votes')


class Clan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(300), default='')
    avatar = db.Column(db.String(200), default='default_clan.png')
    banner = db.Column(db.String(200), default='default_clan_banner.png')
    mode = db.Column(db.String(20), default='open')
    is_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    owner = db.relationship('User', foreign_keys=[owner_id], backref='owned_clan')
    members = db.relationship('ClanMember', backref='clan', cascade='all, delete-orphan')
    posts = db.relationship('ClanPost', backref='clan', cascade='all, delete-orphan')
    invites = db.relationship('ClanInvite', backref='clan', cascade='all, delete-orphan')

    @property
    def rating(self):
        return sum(sum(v.value for v in post.votes) for post in self.posts)


class ClanMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    clan_id = db.Column(db.Integer, db.ForeignKey('clan.id'), nullable=False)
    role = db.Column(db.String(20), default='Участник')
    joined_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref=db.backref('clan_membership', uselist=False))


class ClanInvite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    clan_id = db.Column(db.Integer, db.ForeignKey('clan.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    type = db.Column(db.String(20), default='request')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref='clan_invites')

    __table_args__ = (db.UniqueConstraint('clan_id', 'user_id', name='unique_clan_invite'),)


class ClanPost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    clan_id = db.Column(db.Integer, db.ForeignKey('clan.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    author = db.relationship('User', backref='clan_posts')
    votes = db.relationship('ClanPostVote', backref='post', cascade='all, delete-orphan')

    @property
    def rating(self):
        return sum(v.value for v in self.votes)

    def user_vote(self, user):
        v = ClanPostVote.query.filter_by(user_id=user.id, post_id=self.id).first()
        return v.value if v else 0


class ClanPostVote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('clan_post.id'), nullable=False)
    value = db.Column(db.Integer)

    user = db.relationship('User', backref='clan_post_votes')