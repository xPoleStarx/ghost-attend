"""
GhostAttend — Mock DYS Server

E2E testleri için sahte DYS sunucusu.
Login formu, ders listesi ve sahte Teams linki sağlar.
"""

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI(title="Mock DYS Server")

# Test credentials
VALID_EMAIL = "test@stu.university.edu.tr"
VALID_PASSWORD = "test123"

# Sahte dersler
MOCK_COURSES = [
    {
        "id": 1,
        "name": "Kariyer Planlama",
        "instructor": "Dr. Ahmet Yılmaz",
        "day": "Pazartesi",
        "time": "09:00-10:30",
        "teams_url": "https://teams.microsoft.com/l/meetup-join/mock-meeting-1",
    },
    {
        "id": 2,
        "name": "Veri Yapıları",
        "instructor": "Prof. Ayşe Kaya",
        "day": "Salı",
        "time": "13:00-14:30",
        "teams_url": "https://teams.microsoft.com/l/meetup-join/mock-meeting-2",
    },
    {
        "id": 3,
        "name": "İngilizce",
        "instructor": "Öğr. Gör. John Smith",
        "day": "Çarşamba",
        "time": "10:00-11:30",
        "teams_url": None,  # Link paylaşılmamış
    },
]


@app.get("/", response_class=HTMLResponse)
async def login_page():
    """DYS login sayfası."""
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Mock DYS - Giriş</title></head>
    <body>
        <h1>Üniversite Öğrenci Bilgi Sistemi</h1>
        <h2>Giriş Yap</h2>
        <form method="post" action="/login">
            <label for="email">E-posta:</label><br>
            <input type="email" id="email" name="email" placeholder="ornek@stu.university.edu.tr"><br><br>
            <label for="password">Şifre:</label><br>
            <input type="password" id="password" name="password"><br><br>
            <button type="submit" id="login-btn">Giriş Yap</button>
        </form>
    </body>
    </html>
    """


@app.post("/login")
async def login(email: str = Form(...), password: str = Form(...)):
    """Login işlemi."""
    if email == VALID_EMAIL and password == VALID_PASSWORD:
        return RedirectResponse(url="/dashboard", status_code=303)
    return HTMLResponse(
        content="""
        <html><body>
            <h1>Giriş Başarısız</h1>
            <p style="color: red;">E-posta veya şifre hatalı.</p>
            <a href="/">Tekrar dene</a>
        </body></html>
        """,
        status_code=200,
    )


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Ana panel — giriş sonrası."""
    return """
    <html><body>
        <h1>Öğrenci Paneli</h1>
        <nav>
            <a href="/courses" id="my-courses">📚 Derslerim</a> |
            <a href="/schedule" id="schedule">📅 Ders Programı</a> |
            <a href="/announcements">📢 Duyurular</a>
        </nav>
        <p>Hoş geldiniz!</p>
    </body></html>
    """


@app.get("/courses", response_class=HTMLResponse)
async def courses_list():
    """Ders listesi."""
    course_items = ""
    for c in MOCK_COURSES:
        course_items += f"""
        <div class="course" id="course-{c['id']}">
            <h3><a href="/course/{c['id']}">{c['name']}</a></h3>
            <p>👨‍🏫 {c['instructor']}</p>
            <p>📅 {c['day']} {c['time']}</p>
        </div>
        <hr>
        """

    return f"""
    <html><body>
        <h1>📚 Derslerim</h1>
        <a href="/dashboard">← Panele Dön</a>
        {course_items}
    </body></html>
    """


@app.get("/course/{course_id}", response_class=HTMLResponse)
async def course_detail(course_id: int):
    """Ders detay sayfası."""
    course = next((c for c in MOCK_COURSES if c["id"] == course_id), None)

    if not course:
        return HTMLResponse("<h1>Ders bulunamadı</h1>", status_code=404)

    meeting_section = ""
    if course["teams_url"]:
        meeting_section = f"""
        <div id="meeting-section">
            <h3>🖥️ Canlı Ders</h3>
            <a href="{course['teams_url']}" id="join-meeting" class="meeting-link"
               target="_blank">
                Toplantıya Katıl (Teams)
            </a>
        </div>
        """
    else:
        meeting_section = """
        <div id="meeting-section">
            <h3>🖥️ Canlı Ders</h3>
            <p>Henüz canlı ders linki paylaşılmamış.</p>
        </div>
        """

    return f"""
    <html><body>
        <h1>{course['name']}</h1>
        <a href="/courses">← Derslerime Dön</a>
        <p>👨‍🏫 {course['instructor']}</p>
        <p>📅 {course['day']} {course['time']}</p>
        {meeting_section}
        <hr>
        <h3>📢 Duyurular</h3>
        <p>Bu hafta için duyuru yok.</p>
        <h3>📁 Ders Materyalleri</h3>
        <p>Henüz materyal yüklenmemiş.</p>
    </body></html>
    """


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "ok", "service": "mock-dys"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8888)
