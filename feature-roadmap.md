# Feature Roadmap

## Phase 1: Infrastructure

1. **Project Initialization**
   - Initialize repository structure for frontend and backend
   - Add README and initial documentation

2. **Docker Compose Setup**
   - Create `docker-compose.yml` to orchestrate frontend (React), backend (FastAPI), and Nginx
   - Add Dockerfiles for frontend and backend

3. **Backend Setup**
   - Scaffold FastAPI app
   - Add requirements.txt and install dependencies
   - Create a simple `/api/hello` endpoint returning a "Hello, world!" message from the SQLite Database

4. **Frontend Setup**
   - Scaffold React app with Bun, Tailwind CSS, and DaisyUI
   - Add a page/component that fetches from `/api/hello` and displays the result

5. **Nginx Setup**
   - Configure Nginx as a reverse proxy for frontend and backend
   - Set up static file serving for frontend

6. **Let's Encrypt Integration**
   - Configure Nginx for HTTPS using Let's Encrypt (staging/test certificates for development)
   - Set up automatic certificate renewal (e.g., with a cron job or certbot renew script in Docker)

7. **End-to-End Test**
   - Verify frontend can communicate with backend through Nginx using Docker Compose
   - Confirm "Hello, world!" is displayed in the frontend

---

## Phase 2: MVP Features

1. **User Authentication**
   - FastAPI backend endpoints for sign up, login, password reset
   - JWT-based authentication
   - React forms for authentication (styled with Tailwind CSS/DaisyUI)

2. **User Dashboard**
   - React dashboard page to view personal drafts
   - Create new draft (frontend form, backend endpoint)

3. **Draft Management**
   - Add/edit/remove draft picks (React UI, FastAPI endpoints)
   - Invite friends to drafts (email or invite link generation)

4. **Draft Board View**
   - Real-time updates (consider WebSockets or polling with FastAPI)
   - Pick history (displayed in React, data from backend)

---

## Phase 3: Enhancements

1. **Notifications**
   - In-app notifications (React components)
   - Optional: Email notifications (FastAPI integration)

2. **User Profiles**
   - Custom avatars (file upload via FastAPI, display in React)
   - Profile settings page

3. **Analytics**
   - Draft statistics (backend aggregation, frontend charts)
   - Leaderboards

---

## Phase 4: Stretch Goals

1. **Mobile App**
   - React Native or PWA (Progressive Web App) support

2. **Third-party Integrations**
   - Social media sharing (frontend integration)
   - External data sources (e.g., player stats APIs)

---

*This roadmap is subject to change as requirements evolve.*
