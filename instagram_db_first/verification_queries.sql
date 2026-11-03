-- After test sign-ups / uploads on the web, run these in MySQL Workbench.
USE instagram_term_2026;

-- 1. Schema checks
SHOW TABLES;
SHOW CREATE TABLE follows;
SHOW CREATE TABLE posts;

-- 2. Check actual stored data and FK connections
SELECT 'users' AS relation_name, COUNT(*) AS tuple_count FROM users
UNION ALL SELECT 'follows', COUNT(*) FROM follows
UNION ALL SELECT 'posts', COUNT(*) FROM posts
UNION ALL SELECT 'comments', COUNT(*) FROM comments;

-- 3. Join posts to their author (no user name duplication in posts)
SELECT p.post_id, u.user_id, u.display_name, p.caption, p.created_at
FROM posts p JOIN users u ON p.author_id = u.user_id
ORDER BY p.created_at DESC, p.post_id DESC;

-- 4. Follower counts derived from relationship rows
SELECT u.user_id, COUNT(f.follower_id) AS followers
FROM users u LEFT JOIN follows f ON u.user_id = f.followee_id
GROUP BY u.user_id
ORDER BY followers DESC, u.user_id;

-- 5. Key feed query (replace alice with a real user_id)
SELECT p.post_id, p.author_id, p.caption, p.created_at
FROM posts p
WHERE p.author_id = 'alice'
   OR EXISTS (SELECT 1 FROM follows f
              WHERE f.follower_id = 'alice' AND f.followee_id = p.author_id)
ORDER BY p.created_at DESC, p.post_id DESC;
