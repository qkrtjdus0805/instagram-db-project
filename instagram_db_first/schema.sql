-- 2026 DB Term Project: minimal Instagram-style photo-sharing database.
-- Does NOT delete or modify MYDB, university_lab1, or old instagram databases.
CREATE DATABASE IF NOT EXISTS instagram_term_2026
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE instagram_term_2026;

-- Base relation: independent user accounts.
CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(32) NOT NULL,
    display_name VARCHAR(60) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_users PRIMARY KEY (user_id)
) ENGINE=InnoDB;

-- A directed many-to-many self-relationship on users.
CREATE TABLE IF NOT EXISTS follows (
    follower_id VARCHAR(32) NOT NULL,
    followee_id VARCHAR(32) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_follows PRIMARY KEY (follower_id, followee_id),
    CONSTRAINT fk_follows_follower FOREIGN KEY (follower_id)
        REFERENCES users(user_id) ON DELETE CASCADE,
    CONSTRAINT fk_follows_followee FOREIGN KEY (followee_id)
        REFERENCES users(user_id) ON DELETE CASCADE,
    CONSTRAINT chk_follows_no_self CHECK (follower_id <> followee_id),
    INDEX idx_follows_followee (followee_id)
) ENGINE=InnoDB;

-- Image bytes live on disk; image_path is the relative public URL.
CREATE TABLE IF NOT EXISTS posts (
    post_id BIGINT NOT NULL AUTO_INCREMENT,
    author_id VARCHAR(32) NOT NULL,
    image_path VARCHAR(255) NOT NULL,
    caption VARCHAR(500) NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_posts PRIMARY KEY (post_id),
    CONSTRAINT fk_posts_author FOREIGN KEY (author_id)
        REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_posts_author_time (author_id, created_at, post_id),
    INDEX idx_posts_time (created_at, post_id)
) ENGINE=InnoDB;

-- @mentions are retained as plain text in body (no notifications required).
CREATE TABLE IF NOT EXISTS comments (
    comment_id BIGINT NOT NULL AUTO_INCREMENT,
    post_id BIGINT NOT NULL,
    author_id VARCHAR(32) NOT NULL,
    body VARCHAR(1000) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_comments PRIMARY KEY (comment_id),
    CONSTRAINT fk_comments_post FOREIGN KEY (post_id)
        REFERENCES posts(post_id) ON DELETE CASCADE,
    CONSTRAINT fk_comments_author FOREIGN KEY (author_id)
        REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_comments_post_time (post_id, created_at, comment_id)
) ENGINE=InnoDB;
