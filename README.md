# PopActaDraftApp

## Overview
PopActaDraftApp is a web application designed to manage your fantasy football snake draft.

## Getting Started

### Prerequisites
- Python 3.10+ (recommended)
- FastAPI
- Node.js (version 18+ recommended)
- Bun (instead of npm or yarn)
- SQLite
- Docker
- Docker Compose
- Nginx
- Let's Encrypt (for SSL certificates)
- [Other dependencies as needed]

### Setup
```bash
git clone https://github.com/yourusername/PopActaDraftApp.git
cd PopActaDraftApp
# Create and activate a virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
pip install -r requirements.txt
# To run the FastAPI app:
uvicorn app.main:app --reload

# Frontend setup (React/Tailwind/DaisyUI)
cd frontend
bun install
bun run dev

# For production, use Docker Compose to orchestrate FastAPI, frontend, and Nginx:
cd ..
docker-compose up --build
```

## Design Restrictions
- Must be responsive and mobile-friendly.
- Use only open-source libraries.
- No user data stored without consent.
- All API endpoints must be authenticated.
- [Add any other relevant restrictions]

## Stack Definitions

**Frontend:**
- Framework: React (with TypeScript)
- Styling: Tailwind CSS
- UI Library: DaisyUI
- Package Manager: Bun

**Backend:**
- Python with FastAPI
- Database: SQLite

**Containerization & Web Server:**
- Docker & Docker Compose for orchestration
- Nginx as reverse proxy and static file server
- Let's Encrypt for SSL/TLS certificates

**Other:**
- Hosting: [e.g., Docker, Vercel, Heroku, AWS]
- Version Control: GitHub

## Project Structure

```
PopActaDraftApp/
backend/
├── app/
│   ├── services/
│   |   ├── player_import.py
│   ├── __init__.py
│   ├── database.py          # Database connection and session management
│   └── init_db.py           # Database initialization script
│   ├── main.py
│   ├── models.py            # SQLAlchemy models
├── data/
│   └── app.db               # SQLite database file (created automatically)
├── migrations/              # Optional: for future schema changes
└── Dockerfile               # Backend Dockerfile
└── requirements.txt
├── frontend/                # React frontend (with Bun, Tailwind CSS, DaisyUI)
│   ├── dist/
│   ├── node_modules/
│   ├── public/
│   │   └── index.html
│   ├── src/
│   |   ├── components/
│   │   |       └── Navbar.tsx
│   │   |       └── SearchModal.tsx
│   │   |       └── WelcomeStrip.tsx
│   |   ├── pages/
│   │   |       └── Draft.tsx
│   │   |       └── Home.tsx
│   │   |       └── Players.tsx
│   │   |       └── Settings.tsx
│   │   └── App.tsx
│   │   └── index.css
│   │   └── main.tsx
│   ├── build.ts
│   ├── build-env.d.ts
│   ├── bunfig.toml
│   ├── package.json
│   ├── tailwind.config.js
├── nginx/                  # Nginx configuration
│   └── nginx.conf
│   └── Dockerfile
├── docker-compose.yml      # Docker Compose orchestration
├── README.md
└── feature-roadmap.md
```

## License
[Specify license, e.g., MIT]
