"""DB-first Instagram lab: only the 2026 term project's required features."""
import hmac
import io
import os
import re
import secrets
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image, UnidentifiedImageError
from starlette.middleware.sessions import SessionMiddleware

import db
from security import check_password, make_password_hash

load_dotenv()
BASE = Path(__file__).resolve().parent
UPLOADS = BASE / "uploads"
UPLOADS.mkdir(exist_ok=True)
MAX_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

app = FastAPI(title="DB Term Project – Instagram")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET") or secrets.token_urlsafe(32),
    same_site="lax",
    https_only=False,  # Localhost only; use HTTPS and True for public deployment.
)
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOADS)), name="uploads")
templates = Jinja2Templates(directory=str(BASE / "templates"))


def csrf_token(request: Request) -> str:
    if "csrf" not in request.session:
        request.session["csrf"] = secrets.token_urlsafe(24)
    return request.session["csrf"]


def require_csrf(request: Request, submitted: str):
    saved = request.session.get("csrf", "")
    if not saved or not hmac.compare_digest(saved, submitted):
        raise HTTPException(status_code=403, detail="Invalid form token")


def render(request: Request, name: str, *, status_code=200, **context):
    return templates.TemplateResponse(
        request=request,
        name=name,
        context={
            "current_user": request.session.get("user_id"),
            "csrf": csrf_token(request),
            **context,
        },
        status_code=status_code,
    )


def redirect(path: str):
    return RedirectResponse(path, status_code=303)


def logged_in(request: Request):
    return request.session.get("user_id")


@app.get("/")
def index(request: Request):
    return redirect("/feed" if logged_in(request) else "/login")


@app.get("/signup")
def signup_page(request: Request):
    return render(request, "signup.html")


@app.post("/signup")
def signup(
    request: Request,
    user_id: str = Form(...),
    display_name: str = Form(...),
    password: str = Form(...),
    csrf: str = Form(...),
):
    require_csrf(request, csrf)
    user_id = user_id.strip()
    display_name = display_name.strip()
    if not re.fullmatch(r"[a-zA-Z0-9_]{3,32}", user_id):
        return render(request, "signup.html", error="아이디는 3~32자의 영문·숫자·_만 가능해요.", status_code=400)
    if not 1 <= len(display_name) <= 60 or len(password) < 8 or len(password) > 200:
        return render(request, "signup.html", error="닉네임은 1~60자, 비밀번호는 8~200자로 입력해 주세요.", status_code=400)
    if db.one("SELECT user_id FROM users WHERE user_id = %s", (user_id,)):
        return render(request, "signup.html", error="이미 사용 중인 아이디입니다.", status_code=400)
    # The PK also prevents duplicate accounts if two requests race.
    try:
        db.change(
            "INSERT INTO users (user_id, display_name, password_hash) VALUES (%s, %s, %s)",
            (user_id, display_name, make_password_hash(password)),
        )
    except Exception as exc:
        # Distinguish duplicate PK from other DB failures; do not hide real problems.
        if getattr(exc, "errno", None) == 1062:
            return render(request, "signup.html", error="이미 사용 중인 아이디입니다.", status_code=400)
        raise
    request.session.clear()
    request.session["user_id"] = user_id
    return redirect("/feed")


@app.get("/login")
def login_page(request: Request):
    return render(request, "login.html")


@app.post("/login")
def login(
    request: Request,
    user_id: str = Form(...),
    password: str = Form(...),
    csrf: str = Form(...),
):
    require_csrf(request, csrf)
    account = db.one("SELECT user_id, password_hash FROM users WHERE user_id = %s", (user_id.strip(),))
    if account is None or not check_password(password, account["password_hash"]):
        return render(request, "login.html", error="아이디 또는 비밀번호가 올바르지 않습니다.", status_code=401)
    request.session.clear()
    request.session["user_id"] = account["user_id"]
    return redirect("/feed")


@app.post("/logout")
def logout(request: Request, csrf: str = Form(...)):
    require_csrf(request, csrf)
    request.session.clear()
    return redirect("/login")


@app.get("/settings")
def settings_page(request: Request):
    if not logged_in(request):
        return redirect("/login")
    return render(request, "settings.html")


@app.post("/settings/password")
def change_password(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...),
    csrf: str = Form(...),
):
    require_csrf(request, csrf)
    me = logged_in(request)
    if not me:
        return redirect("/login")
    account = db.one("SELECT password_hash FROM users WHERE user_id=%s", (me,))
    if not account or not check_password(old_password, account["password_hash"]):
        return render(request, "settings.html", error="기존 비밀번호가 틀렸습니다.", status_code=400)
    if not 8 <= len(new_password) <= 200:
        return render(request, "settings.html", error="새 비밀번호는 8~200자로 입력해 주세요.", status_code=400)
    db.change("UPDATE users SET password_hash=%s WHERE user_id=%s", (make_password_hash(new_password), me))
    return render(request, "settings.html", message="비밀번호가 변경됐습니다.")


@app.get("/feed")
def feed(request: Request):
    me = logged_in(request)
    if not me:
        return redirect("/login")
    # Key course query: self + followed accounts, newest posts first.
    posts = db.all_rows(
        """SELECT p.post_id, p.author_id, u.display_name, p.caption, p.image_path, p.created_at
             FROM posts AS p
             JOIN users AS u ON u.user_id = p.author_id
             WHERE p.author_id = %s
                OR EXISTS (
                   SELECT 1 FROM follows AS f
                   WHERE f.follower_id = %s AND f.followee_id = p.author_id
                )
             ORDER BY p.created_at DESC, p.post_id DESC
             LIMIT 100""",
        (me, me),
    )
    return render(request, "feed.html", posts=posts)


@app.get("/users")
def users(request: Request):
    me = logged_in(request)
    if not me:
        return redirect("/login")
    people = db.all_rows(
        "SELECT user_id, display_name FROM users WHERE user_id<>%s ORDER BY user_id LIMIT 100",
        (me,),
    )
    return render(request, "users.html", people=people)


@app.get("/users/{user_id}")
def profile(request: Request, user_id: str):
    me = logged_in(request)
    if not me:
        return redirect("/login")
    person = db.one(
        """SELECT u.user_id, u.display_name,
                  (SELECT COUNT(*) FROM follows f WHERE f.followee_id=u.user_id) AS follower_count,
                  (SELECT COUNT(*) FROM follows f WHERE f.follower_id=u.user_id) AS following_count
           FROM users u WHERE u.user_id=%s""",
        (user_id,),
    )
    if not person:
        raise HTTPException(status_code=404, detail="User not found")
    posts = db.all_rows(
        """SELECT post_id, caption, image_path, created_at FROM posts
             WHERE author_id=%s ORDER BY created_at DESC, post_id DESC LIMIT 100""",
        (user_id,),
    )
    following = False if me == user_id else bool(db.one(
        "SELECT 1 FROM follows WHERE follower_id=%s AND followee_id=%s", (me, user_id)
    ))
    return render(request, "profile.html", person=person, posts=posts, is_following=following)


@app.post("/users/{user_id}/follow")
def follow(request: Request, user_id: str, csrf: str = Form(...)):
    require_csrf(request, csrf)
    me = logged_in(request)
    if not me:
        return redirect("/login")
    if me == user_id:
        raise HTTPException(status_code=400, detail="Cannot follow yourself")
    if not db.one("SELECT 1 FROM users WHERE user_id=%s", (user_id,)):
        raise HTTPException(status_code=404, detail="User not found")
    db.change(
        "INSERT IGNORE INTO follows (follower_id, followee_id) VALUES (%s,%s)",
        (me, user_id),
    )
    return redirect(f"/users/{user_id}")


@app.post("/users/{user_id}/unfollow")
def unfollow(request: Request, user_id: str, csrf: str = Form(...)):
    require_csrf(request, csrf)
    me = logged_in(request)
    if not me:
        return redirect("/login")
    db.change("DELETE FROM follows WHERE follower_id=%s AND followee_id=%s", (me, user_id))
    return redirect(f"/users/{user_id}")


@app.get("/users/{user_id}/connections")
def connections(request: Request, user_id: str, kind: str = "followers"):
    if not logged_in(request):
        return redirect("/login")
    if kind not in ("followers", "following"):
        raise HTTPException(status_code=400, detail="Invalid list kind")
    if not db.one("SELECT 1 FROM users WHERE user_id=%s", (user_id,)):
        raise HTTPException(status_code=404, detail="User not found")
    if kind == "followers":
        sql = """SELECT u.user_id, u.display_name FROM follows f
                 JOIN users u ON u.user_id=f.follower_id
                 WHERE f.followee_id=%s ORDER BY u.user_id"""
    else:
        sql = """SELECT u.user_id, u.display_name FROM follows f
                 JOIN users u ON u.user_id=f.followee_id
                 WHERE f.follower_id=%s ORDER BY u.user_id"""
    people = db.all_rows(sql, (user_id,))
    return render(request, "connections.html", people=people, user_id=user_id, kind=kind)


@app.get("/posts/new")
def new_post_page(request: Request):
    if not logged_in(request):
        return redirect("/login")
    return render(request, "new_post.html")


@app.post("/posts")
async def create_post(
    request: Request,
    image: UploadFile = File(...),
    caption: str = Form(""),
    csrf: str = Form(...),
):
    require_csrf(request, csrf)
    me = logged_in(request)
    if not me:
        return redirect("/login")
    if len(caption) > 500:
        return render(request, "new_post.html", error="설명은 최대 500자입니다.", status_code=400)
    # Allow only verified image data, never trust the browser's filename/extension.
    content = await image.read(MAX_BYTES + 1)
    await image.close()
    if len(content) > MAX_BYTES:
        return render(request, "new_post.html", error="사진은 5MB 이하만 업로드할 수 있어요.", status_code=400)
    try:
        with Image.open(io.BytesIO(content)) as picture:
            if picture.width * picture.height > MAX_IMAGE_PIXELS:
                raise ValueError("too many pixels")
            fmt = picture.format
            picture.verify()
        extension = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}.get(fmt)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        extension = None
    if not extension:
        return render(request, "new_post.html", error="JPG, PNG, WEBP 이미지 파일만 가능합니다.", status_code=400)
    filename = f"{uuid.uuid4().hex}.{extension}"
    path = UPLOADS / filename
    path.write_bytes(content)
    try:
        post_id = db.change(
            "INSERT INTO posts (author_id, image_path, caption) VALUES (%s, %s, %s)",
            (me, f"/uploads/{filename}", caption.strip()),
        )
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return redirect(f"/posts/{post_id}")


@app.get("/posts/{post_id}")
def post_detail(request: Request, post_id: int):
    if not logged_in(request):
        return redirect("/login")
    post = db.one(
        """SELECT p.post_id, p.author_id, p.caption, p.image_path, p.created_at, u.display_name
             FROM posts p JOIN users u ON u.user_id=p.author_id WHERE p.post_id=%s""",
        (post_id,),
    )
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    comments = db.all_rows(
        """SELECT c.body, c.created_at, c.author_id, u.display_name
             FROM comments c JOIN users u ON c.author_id=u.user_id
             WHERE c.post_id=%s ORDER BY c.created_at ASC, c.comment_id ASC""",
        (post_id,),
    )
    return render(request, "post.html", post=post, comments=comments)


@app.post("/posts/{post_id}/comments")
def add_comment(
    request: Request,
    post_id: int,
    body: str = Form(...),
    csrf: str = Form(...),
):
    require_csrf(request, csrf)
    me = logged_in(request)
    if not me:
        return redirect("/login")
    body = body.strip()
    if not 1 <= len(body) <= 1000:
        raise HTTPException(status_code=400, detail="Comment must have 1~1000 characters")
    if not db.one("SELECT 1 FROM posts WHERE post_id=%s", (post_id,)):
        raise HTTPException(status_code=404, detail="Post not found")
    db.change(
        "INSERT INTO comments (post_id, author_id, body) VALUES (%s,%s,%s)",
        (post_id, me, body),
    )
    return redirect(f"/posts/{post_id}")
