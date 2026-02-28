# 🌿 Rubber Plantation Management System

A full-featured web application for managing rubber plantations — built with Django, PostGIS, and deployed on AWS EC2 using Docker and GitHub Actions CI/CD.

## 🚀 Live Demo

**Production URL:** http://98.92.46.51

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Django 6.0.2 |
| **Database** | PostgreSQL + PostGIS |
| **Maps** | GeoDjango + Leaflet.js |
| **Web Server** | Gunicorn |
| **Static Files** | WhiteNoise |
| **Containerization** | Docker + Docker Compose |
| **CI/CD** | GitHub Actions |
| **Cloud Hosting** | AWS EC2 (Ubuntu) |

---

## ✨ Features

- 🗺️ **Interactive Map** — View and manage rubber plantation blocks with Leaflet maps
- 👷 **Tapper Dashboard** — Tappers can log daily latex collection
- 👔 **Manager Dashboard** — Managers can monitor blocks, tappers, and reports
- 🛡️ **Admin Panel** — Full system control for administrators
- 📊 **Reports** — Generate yield and performance reports
- ☁️ **Weather Integration** — Real-time weather data via API

---

## ⚙️ Local Development Setup

### Prerequisites
- Python 3.12
- PostgreSQL 15 with PostGIS extension
- Docker Desktop (optional)

### 1. Clone the Repository
```bash
git clone https://github.com/ashishprince/rubbersystem.git
cd rubbersystem
```

### 2. Create Virtual Environment
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment
Create a `.env` file in the project root:
```env
WEATHER_API_KEY=your_weather_api_key_here
```

### 5. Set Up Database
```bash
python manage.py migrate
python manage.py createsuperuser
```

### 6. Run the Development Server
```bash
python manage.py runserver
```

---

## 🐳 Docker Setup (Local)

```bash
docker compose up --build
```

The app will be available at `http://localhost:8000`.

---

## ☁️ AWS Deployment

This project uses **GitHub Actions** to automatically build and deploy to AWS EC2 on every push to `main`.

### Required GitHub Secrets

| Secret | Value |
|--------|-------|
| `HOST` | EC2 public IP address |
| `USERNAME` | `ubuntu` |
| `SSH_KEY` | Contents of your `.pem` file |
| `DOCKER_USERNAME` | Docker Hub username |
| `DOCKER_PASSWORD` | Docker Hub access token |

### Deployment Flow

```
git push origin main
       ↓
GitHub Actions triggers
       ↓
Docker image built & pushed to Docker Hub
       ↓
SSH into EC2 instance
       ↓
Pull latest image → Restart container → Run migrations
       ↓
App is live at http://YOUR_EC2_IP
```

---

## 📁 Project Structure

```
rubberplantation/
├── core/               # Main application (models, views, templates)
├── rubber_system/      # Django project settings
├── static/             # CSS, JS, images
├── templates/          # HTML templates
├── .github/workflows/  # GitHub Actions CI/CD
├── Dockerfile          # Docker image definition
├── docker-compose.yml  # Local development orchestration
└── requirements.txt    # Python dependencies
```

---

## 👤 Author

**Ashish** — [GitHub](https://github.com/ashishprince)
